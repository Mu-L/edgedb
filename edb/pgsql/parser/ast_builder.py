#
# This source file is part of the EdgeDB open source project.
#
# Copyright 2010-present MagicStack Inc. and the EdgeDB authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


import dataclasses
from typing import (
    Any,
    Callable,
    Optional,
    Sequence,
    cast,
)

from edb.common import span
from edb.common.parsing import Span

from edb.pgsql import ast as pgast
from edb.edgeql import ast as qlast
from edb.pgsql.parser.exceptions import PSqlUnsupportedError, get_node_name


@dataclasses.dataclass(kw_only=True)
class Context:
    source_sql: str
    has_fallback = False


# Node = bool | str | int | float | List[Any] | dict[str, Any]
Node = Any


def build_stmts(
    node: Node, source_sql: str, propagate_spans: bool
) -> list[pgast.Query | pgast.Statement]:
    ctx = Context(source_sql=source_sql)

    try:
        res = [_build_stmt(node["stmt"], ctx) for node in node["stmts"]]
    except IndexError:
        raise PSqlUnsupportedError()
    except PSqlUnsupportedError as e:
        if e.node and "location" in e.node:
            e.location = e.node["location"]
            assert e.location
            e.message += f" near location {e.location}:"
            e.message += source_sql[e.location : (e.location + 50)]
        raise

    if propagate_spans:
        # we need to do a full pass of span propagation, because some
        # nodes (CommonTableExpr) have span, but their children don't (Insert).
        span.SpanPropagator(full_pass=True).container_visit(res)

    return res


def _maybe[T](
    node: Node, ctx: Context, name: str, builder: Callable[[Node, Context], T]
) -> Optional[T]:
    if name in node:
        return builder(node[name], ctx)
    return None


def _ident(t: Any) -> Any:
    return t


def _list[T, U](
    node: Node,
    ctx: Context,
    name: str,
    builder: Callable[[Node, Context], T],
    mapper: Callable[[T], U] = _ident,
    *,
    unwrap: Optional[str] = None,
) -> list[U]:
    if unwrap is not None:
        return [
            mapper(builder(_unwrap(n, unwrap), ctx)) for n in node.get(name, [])
        ]
    else:
        return [mapper(builder(n, ctx)) for n in node.get(name, [])]


def _maybe_list[T, U](
    node: Node,
    ctx: Context,
    name: str,
    builder: Callable[[Node, Context], T],
    mapper: Callable[[T], U] = _ident,
    *,
    unwrap: Optional[str] = None,
) -> Optional[list[U]]:
    return (
        _list(node, ctx, name, builder, mapper, unwrap=unwrap)
        if name in node
        else None
    )


def _enum[T](
    _ty: type[T],
    node: Node,
    ctx: Context,
    builders: dict[str, Callable[[Node, Context], T]],
    fallbacks: Sequence[Callable[[Node, Context], T]] = (),
) -> T:
    outer_fallback = ctx.has_fallback
    ctx.has_fallback = False

    try:
        for name in builders:
            if name in node:
                builder = builders[name]
                return builder(node[name], ctx)

        ctx.has_fallback = True
        for fallback in fallbacks:
            res = fallback(node, ctx)
            if res:
                return res

        if outer_fallback:
            return None  # type: ignore

        raise PSqlUnsupportedError(
            node, ", ".join(get_node_name(k) for k in node.keys())
        )
    finally:
        ctx.has_fallback = outer_fallback


def _build_str(node: Node, _: Context) -> str:
    node = _unwrap_string(node)
    return str(node)


def _build_bool(node: Node, _: Context) -> bool:
    assert isinstance(node, bool)
    return node


def _bool_or_false(node: Node, name: str) -> bool:
    return node[name] if name in node else False


def _unwrap(node: Node, name: str) -> Node:
    if isinstance(node, dict) and name in node:
        return node[name]
    return node


def _unwrap_boolean(n: Node) -> Node:
    n = _unwrap(n, 'Boolean')
    n = _unwrap(n, 'str')
    n = _unwrap(n, 'boolval')
    n = _unwrap(n, 'boolval')
    if isinstance(n, dict) and len(n) == 0:
        n = False
    return n


def _unwrap_int(n: Node) -> Node:
    n = _unwrap(n, 'Integer')
    n = _unwrap(n, 'str')
    n = _unwrap(n, 'ival')
    n = _unwrap(n, 'ival')
    if isinstance(n, dict) and len(n) == 0:
        n = 0
    return n


def _unwrap_float(n: Node) -> Node:
    n = _unwrap(n, 'Float')
    n = _unwrap(n, 'str')
    n = _unwrap(n, 'fval')
    n = _unwrap(n, 'fval')
    return n


def _unwrap_string(n: Node) -> Node:
    n = _unwrap(n, 'String')
    n = _unwrap(n, 'str')
    n = _unwrap(n, 'sval')
    n = _unwrap(n, 'sval')
    return n


def _as_column_ref(name: str) -> pgast.ColumnRef:
    return pgast.ColumnRef(
        name=(name,),
    )


def _build_span(n: Node, c: Context) -> Optional[Span]:
    if 'location' not in n:
        return None

    return Span(
        filename=None,
        buffer=c.source_sql,
        start=n["location"],
        end=n["location"],
    )


def _build_stmt(node: Node, c: Context) -> pgast.Query | pgast.Statement:
    return _enum(
        pgast.Query | pgast.Statement,  # type: ignore
        node,
        c,
        {
            "VariableSetStmt": _build_variable_set_stmt,
            "VariableShowStmt": _build_variable_show_stmt,
            "TransactionStmt": _build_transaction_stmt,
            "PrepareStmt": _build_prepare,
            "ExecuteStmt": _build_execute,
            "DeallocateStmt": _build_deallocate,
            "CreateStmt": _build_create,
            "CreateTableAsStmt": _build_create_table_as,
            "LockStmt": _build_lock,
            "CopyStmt": _build_copy,
        },
        [_build_query],
    )


def _build_query(node: Node, c: Context) -> pgast.Query:
    return _enum(
        pgast.Query,
        node,
        c,
        {
            "SelectStmt": _build_select_stmt,
            "InsertStmt": _build_insert_stmt,
            "UpdateStmt": _build_update_stmt,
            "DeleteStmt": _build_delete_stmt,
        },
    )


def _build_select_stmt(n: Node, c: Context) -> pgast.SelectStmt:
    op = _maybe(n, c, "op", _build_str)
    if op:
        op = op[6:]
        if op == "NONE":
            op = None
    return pgast.SelectStmt(
        distinct_clause=(
            _maybe(n, c, "distinctClause", _build_distinct)  # type: ignore
        ),
        target_list=_maybe_list(n, c, "targetList", _build_res_target) or [],
        from_clause=_maybe_list(n, c, "fromClause", _build_base_range_var)
        or [],
        where_clause=_maybe(n, c, "whereClause", _build_base_expr),
        group_clause=_maybe_list(n, c, "groupClause", _build_base),
        having_clause=_maybe(n, c, "havingClause", _build_base_expr),
        window_clause=_maybe_list(n, c, "windowClause", _build_base),
        values=_maybe_list(n, c, "valuesLists", _build_base_expr),
        sort_clause=_maybe_list(n, c, "sortClause", _build_sort_by),
        limit_offset=_maybe(n, c, "limitOffset", _build_base_expr),
        limit_count=_maybe(n, c, "limitCount", _build_base_expr),
        locking_clause=_maybe_list(
            n, c, "lockingClause", _build_locking_clause
        ),
        op=op,
        all=n["all"] if "all" in n else False,
        larg=_maybe(n, c, "larg", _build_select_stmt),
        rarg=_maybe(n, c, "rarg", _build_select_stmt),
        ctes=_maybe(n, c, "withClause", _build_ctes),
    )


def _build_insert_stmt(n: Node, c: Context) -> pgast.InsertStmt:
    select_stmt = _maybe(n, c, "selectStmt", _build_stmt)
    assert select_stmt is None or isinstance(select_stmt, pgast.Query)

    return pgast.InsertStmt(
        relation=_build_rel_range_var(n["relation"], c),
        returning_list=(
            _maybe_list(n, c, "returningList", _build_res_target) or []
        ),
        cols=_maybe_list(n, c, "cols", _build_insert_target),
        select_stmt=select_stmt,
        on_conflict=_maybe(n, c, "onConflictClause", _build_on_conflict),
        ctes=_maybe(n, c, "withClause", _build_ctes),
    )


def _build_update_stmt(n: Node, c: Context) -> pgast.UpdateStmt:
    return pgast.UpdateStmt(
        relation=_build_rel_range_var(n["relation"], c),
        targets=_maybe(n, c, "targetList", _build_update_targets) or [],
        where_clause=_maybe(n, c, "whereClause", _build_base_expr),
        from_clause=(
            _maybe_list(n, c, "fromClause", _build_base_range_var) or []
        ),
        returning_list=(
            _maybe_list(n, c, "returningList", _build_res_target) or []
        ),
        ctes=_maybe(n, c, "withClause", _build_ctes),
    )


def _build_delete_stmt(n: Node, c: Context) -> pgast.DeleteStmt:
    return pgast.DeleteStmt(
        relation=_build_rel_range_var(n["relation"], c),
        returning_list=(
            _maybe_list(n, c, "returningList", _build_res_target) or []
        ),
        where_clause=_maybe(n, c, "whereClause", _build_base_expr),
        using_clause=(
            _maybe_list(n, c, "usingClause", _build_base_range_var) or []
        ),
        ctes=_maybe(n, c, "withClause", _build_ctes),
    )


def _build_lock(n: Node, c: Context) -> pgast.LockStmt:
    MODES = {
        1: 'ACCESS SHARE',
        2: 'ROW SHARE',
        3: 'ROW EXCLUSIVE',
        4: 'SHARE UPDATE EXCLUSIVE',
        5: 'SHARE',
        6: 'SHARE ROW EXCLUSIVE',
        7: 'EXCLUSIVE',
        8: 'ACCESS EXCLUSIVE',
    }

    return pgast.LockStmt(
        relations=_list(n, c, "relations", _build_base_range_var),
        mode=MODES[n['mode']],
        no_wait=_bool_or_false(n, 'nowait'),
    )


def _build_variable_set_stmt(n: Node, c: Context) -> pgast.Statement:
    tx_only_vars = {
        "transaction_isolation",
        "transaction_read_only",
        "transaction_deferrable",
    }
    if n["kind"] == "VAR_RESET":
        return pgast.VariableResetStmt(
            name=n["name"],
            scope=(
                pgast.OptionsScope.TRANSACTION
                if n["name"] in tx_only_vars
                else pgast.OptionsScope.SESSION
            ),
            span=_build_span(n, c),
        )

    if n["kind"] == "VAR_RESET_ALL":
        return pgast.VariableResetStmt(
            name=None,
            scope=pgast.OptionsScope.SESSION,
            span=_build_span(n, c),
        )

    if n["kind"] == "VAR_SET_MULTI":
        name = n["name"]
        if name == "TRANSACTION" or name == "SESSION CHARACTERISTICS":
            return pgast.SetTransactionStmt(
                options=_build_transaction_options(n["args"], c),
                scope=(
                    pgast.OptionsScope.TRANSACTION
                    if name == "TRANSACTION"
                    else pgast.OptionsScope.SESSION
                ),
            )

    if n["kind"] == "VAR_SET_VALUE":
        return pgast.VariableSetStmt(
            name=n["name"],
            args=pgast.ArgsList(args=_list(n, c, "args", _build_base_expr)),
            scope=(
                pgast.OptionsScope.TRANSACTION
                if n["name"] in tx_only_vars
                or ("is_local" in n and n["is_local"])
                else pgast.OptionsScope.SESSION
            ),
            span=_build_span(n, c),
        )

    if n["kind"] == "VAR_SET_DEFAULT":
        return pgast.VariableResetStmt(
            name=n["name"],
            scope=(
                pgast.OptionsScope.TRANSACTION
                if n["name"] in tx_only_vars
                or ("is_local" in n and n["is_local"])
                else pgast.OptionsScope.SESSION
            ),
            span=_build_span(n, c),
        )

    raise PSqlUnsupportedError(n)


def _build_variable_show_stmt(n: Node, c: Context) -> pgast.Statement:
    return pgast.VariableShowStmt(
        name=n["name"],
        span=_build_span(n, c),
    )


def _build_transaction_stmt(n: Node, c: Context) -> pgast.TransactionStmt:
    def begin(n: Node, c: Context) -> pgast.BeginStmt:
        return pgast.BeginStmt(
            options=_maybe(n, c, "options", _build_transaction_options)
        )

    def start(n: Node, c: Context) -> pgast.StartStmt:
        return pgast.StartStmt(
            options=_maybe(n, c, "options", _build_transaction_options)
        )

    def commit(n: Node, _: Context) -> pgast.CommitStmt:
        return pgast.CommitStmt(chain=_bool_or_false(n, "chain"))

    def rollback(n: Node, _: Context) -> pgast.RollbackStmt:
        return pgast.RollbackStmt(chain=_bool_or_false(n, "chain"))

    def savepoint(n: Node, _: Context) -> pgast.SavepointStmt:
        return pgast.SavepointStmt(savepoint_name=n["savepoint_name"])

    def release(n: Node, _: Context) -> pgast.ReleaseStmt:
        return pgast.ReleaseStmt(savepoint_name=n["savepoint_name"])

    def rollback_to(n: Node, _: Context) -> pgast.RollbackToStmt:
        return pgast.RollbackToStmt(savepoint_name=n["savepoint_name"])

    def prepare(n: Node, _: Context) -> pgast.PrepareTransaction:
        return pgast.PrepareTransaction(gid=n["gid"])

    def commit_prepared(n: Node, _: Context) -> pgast.CommitPreparedStmt:
        return pgast.CommitPreparedStmt(gid=n["gid"])

    def rollback_prepared(n: Node, _: Context) -> pgast.RollbackPreparedStmt:
        return pgast.RollbackPreparedStmt(gid=n["gid"])

    kinds = {
        "BEGIN": begin,
        "START": start,
        "COMMIT": commit,
        "ROLLBACK": rollback,
        "SAVEPOINT": savepoint,
        "RELEASE": release,
        "ROLLBACK_TO": rollback_to,
        "PREPARE": prepare,
        "COMMIT_PREPARED": commit_prepared,
        "ROLLBACK_PREPARED": rollback_prepared,
    }

    kind = cast(str, n["kind"]).removeprefix("TRANS_STMT_")
    if kind not in kinds:
        raise PSqlUnsupportedError(n)

    return kinds[kind](n, c)


def _build_transaction_options(
    nodes: list[Node], c: Context
) -> pgast.TransactionOptions:
    options = {}
    for n in nodes:
        if "DefElem" not in n:
            continue
        def_e = n["DefElem"]
        if not ("defname" in def_e and "arg" in def_e):
            continue
        options[def_e["defname"]] = _build_base_expr(def_e["arg"], c)
    return pgast.TransactionOptions(options=options)


def _build_prepare(n: Node, c: Context) -> pgast.PrepareStmt:
    return pgast.PrepareStmt(
        name=n["name"],
        argtypes=_maybe_list(n, c, "argtypes", _build_type_name),
        query=_build_base_relation(n["query"], c),
    )


def _build_execute(n: Node, c: Context) -> pgast.ExecuteStmt:
    return pgast.ExecuteStmt(
        name=n["name"], params=_maybe_list(n, c, "params", _build_base_expr)
    )


def _build_deallocate(n: Node, c: Context) -> pgast.DeallocateStmt:
    return pgast.DeallocateStmt(name=n["name"])


def _build_create_table_as(n: Node, c: Context) -> pgast.CreateTableAsStmt:
    return pgast.CreateTableAsStmt(
        into=_build_create(n['into'], c),
        query=_build_query(n['query'], c),
        with_no_data=_bool_or_false(n['into'], 'skipData'),
    )


def _build_create(n: Node, c: Context) -> pgast.CreateStmt:
    def _build_on_commit(n: str, _c: Context) -> Optional[str]:
        on_commit = n[9:]
        return on_commit if on_commit != 'NOOP' else None

    relation = n['relation'] if 'relation' in n else n['rel']

    return pgast.CreateStmt(
        relation=_build_relation(relation, c),
        table_elements=_maybe_list(n, c, 'tableElts', _build_table_element)
        or [],
        span=_build_span(n, c),
        on_commit=_maybe(n, c, 'oncommit', _build_on_commit),
    )


def _build_table_element(n: Node, c: Context) -> pgast.TableElement:
    return _enum(
        pgast.TableElement,
        n,
        c,
        {
            "ColumnDef": _build_column_def,
        },
    )


def _build_column_def(n: Node, c: Context) -> pgast.ColumnDef:
    is_not_null = False
    default_expr = None
    if 'constraints' in n:
        for constraint in n['constraints']:
            constraint = _unwrap(constraint, 'Constraint')

            if constraint['contype'] == 'CONSTR_NOTNULL':
                is_not_null = True
            if constraint['contype'] == 'CONSTR_DEFAULT':
                is_not_null = True
                default_expr = _maybe(n, c, 'raw_expr', _build_base_expr)

    return pgast.ColumnDef(
        name=n['colname'],
        typename=_build_type_name(n['typeName'], c),
        default_expr=default_expr,
        is_not_null=is_not_null,
        span=_build_span(n, c),
    )


def _build_base(n: Node, c: Context) -> pgast.Base:
    return _enum(
        pgast.Base,
        n,
        c,
        {
            "CommonTableExpr": _build_cte,
        },
        [_build_base_expr],  # type: ignore
    )


def _build_base_expr(node: Node, c: Context) -> pgast.BaseExpr:
    return _enum(
        pgast.BaseExpr,
        node,
        c,
        {
            "ResTarget": _build_res_target,
            "FuncCall": _build_func_call,
            "CoalesceExpr": _build_coalesce,
            "List": _build_implicit_row,
            "A_Expr": _build_a_expr,
            "A_ArrayExpr": _build_array_expr,
            "A_Const": _build_const,
            "A_Indirection": _build_indirection,
            "BoolExpr": _build_bool_expr,
            "CaseExpr": _build_case_expr,
            "TypeCast": _build_type_cast,
            "NullTest": _build_null_test,
            "BooleanTest": _build_boolean_test,
            "RowExpr": _build_row_expr,
            "SubLink": _build_sub_link,
            "ParamRef": _build_param_ref,
            "SetToDefault": _build_keyword("DEFAULT"),  # type: ignore
            "SQLValueFunction": _build_sql_value_function,
            "CollateClause": _build_collate_clause,
            "MinMaxExpr": _build_min_max_expr,
        },
        [_build_base_range_var, _build_indirection_op],  # type: ignore
    )


def _build_distinct(
    nodes: list[Node], c: Context
) -> list[pgast.Base]:
    # For some reason, plain DISTINCT is parsed as [{}]
    # In our AST this is represented by [pgast.Star()]
    if len(nodes) == 1 and len(nodes[0]) == 0:
        return [pgast.Star()]
    return [_build_base_expr(n, c) for n in nodes]


def _build_indirection(n: Node, c: Context) -> pgast.Indirection:
    return pgast.Indirection(
        arg=_build_base_expr(n['arg'], c),
        indirection=_list(n, c, 'indirection', _build_indirection_op),
    )


def _build_indirection_op(n: Node, c: Context) -> pgast.IndirectionOp:
    return _enum(
        pgast.IndirectionOp,  # type: ignore
        n,
        c,
        {
            'A_Indices': _build_index_or_slice,
            'Star': _build_star,
            'ColumnRef': _build_column_ref,
            'String': _build_record_indirection_op,
        },
    )


def _build_record_indirection_op(
    n: Node, c: Context
) -> pgast.RecordIndirectionOp:
    return pgast.RecordIndirectionOp(name=_build_str(n, c))


def _build_ctes(n: Node, c: Context) -> list[pgast.CommonTableExpr]:
    is_recursive = _maybe(n, c, 'recursive', lambda x, _: bool(x)) or False

    ctes: list[pgast.CommonTableExpr] = _list(n, c, "ctes", _build_cte)
    for cte in ctes:
        cte.recursive = is_recursive
    return ctes


def _build_cte(n: Node, c: Context) -> pgast.CommonTableExpr:
    n = _unwrap(n, "CommonTableExpr")

    materialized = None
    if n["ctematerialized"] == "CTEMaterializeAlways":
        materialized = True
    elif n["ctematerialized"] == "CTEMaterializeNever":
        materialized = False

    return pgast.CommonTableExpr(
        name=n["ctename"],
        query=_build_query(n["ctequery"], c),
        recursive=False,
        aliascolnames=_maybe_list(n, c, "aliascolnames", _build_str),
        materialized=materialized,
        span=_build_span(n, c),
    )


def _build_keyword(name: str) -> Callable[[Node, Context], pgast.Keyword]:
    return lambda n, c: pgast.Keyword(name=name, span=_build_span(n, c))


def _build_param_ref(n: Node, c: Context) -> pgast.ParamRef:
    return pgast.ParamRef(number=n.get("number", 0), span=_build_span(n, c))


def _build_collate_clause(n: Node, c: Context) -> pgast.CollateClause:
    return pgast.CollateClause(
        arg=_build_base_expr(n['arg'], c),
        collname='.'.join(_list(n, c, 'collname', _build_str)),
        span=_build_span(n, c),
    )


def _build_min_max_expr(n: Node, c: Context) -> pgast.MinMaxExpr:
    if n['op'] == 'IS_GREATEST':
        op = 'GREATEST'
    elif n['op'] == 'IS_LEAST':
        op = 'LEAST'
    else:
        raise PSqlUnsupportedError(n)

    return pgast.MinMaxExpr(
        op=op,
        args=_list(n, c, 'args', _build_base_expr),
        span=_build_span(n, c),
    )


def _build_sql_value_function(n: Node, c: Context) -> pgast.SQLValueFunction:
    op = n["op"].removeprefix("SVFOP_")

    op_mapping = {
        "CURRENT_DATE": pgast.SQLValueFunctionOP.CURRENT_DATE,
        "CURRENT_TIME": pgast.SQLValueFunctionOP.CURRENT_TIME,
        "CURRENT_TIME_N": pgast.SQLValueFunctionOP.CURRENT_TIME_N,
        "CURRENT_TIMESTAMP": pgast.SQLValueFunctionOP.CURRENT_TIMESTAMP,
        "CURRENT_TIMESTAMP_N": pgast.SQLValueFunctionOP.CURRENT_TIMESTAMP_N,
        "LOCALTIME": pgast.SQLValueFunctionOP.LOCALTIME,
        "LOCALTIME_N": pgast.SQLValueFunctionOP.LOCALTIME_N,
        "LOCALTIMESTAMP": pgast.SQLValueFunctionOP.LOCALTIMESTAMP,
        "LOCALTIMESTAMP_N": pgast.SQLValueFunctionOP.LOCALTIMESTAMP_N,
        "CURRENT_ROLE": pgast.SQLValueFunctionOP.CURRENT_ROLE,
        "CURRENT_USER": pgast.SQLValueFunctionOP.CURRENT_USER,
        "USER": pgast.SQLValueFunctionOP.USER,
        "SESSION_USER": pgast.SQLValueFunctionOP.SESSION_USER,
        "CURRENT_CATALOG": pgast.SQLValueFunctionOP.CURRENT_CATALOG,
        "CURRENT_SCHEMA": pgast.SQLValueFunctionOP.CURRENT_SCHEMA,
    }

    if op not in op_mapping:
        raise PSqlUnsupportedError(n)

    return pgast.SQLValueFunction(
        op=op_mapping[op], arg=_maybe(n, c, "xpr", _build_base_expr)
    )


def _build_sub_link(n: Node, c: Context) -> pgast.SubLink:
    typ = n["subLinkType"]
    if typ == "EXISTS_SUBLINK":
        operator = "EXISTS"
    elif typ == "NOT_EXISTS_SUBLINK":
        operator = "NOT_EXISTS"
    elif typ == "ALL_SUBLINK":
        operator = "ALL"
    elif typ == "ANY_SUBLINK":
        operator = "= ANY"
    elif typ == "EXPR_SUBLINK":
        operator = None
    elif typ == "ARRAY_SUBLINK":
        operator = "ARRAY"
    else:
        raise PSqlUnsupportedError(n)

    return pgast.SubLink(
        operator=operator,
        expr=_build_query(n["subselect"], c),
        test_expr=_maybe(n, c, 'testexpr', _build_base_expr),
        span=_build_span(n, c),
    )


def _build_row_expr(n: Node, c: Context) -> pgast.BaseExpr:
    args: list[pgast.BaseExpr] = (
        _maybe_list(n, c, "args", _build_base_expr) or []
    )

    format = n.get('row_format', None)
    if format in {'COERCE_EXPLICIT_CALL', 'COERCE_EXPLICIT_CAST'}:
        return pgast.RowExpr(args=args, span=_build_span(n, c))
    else:
        return pgast.ImplicitRowExpr(args=args, span=_build_span(n, c))


def _build_boolean_test(n: Node, c: Context) -> pgast.BooleanTest:
    return pgast.BooleanTest(
        arg=_build_base_expr(n["arg"], c),
        negated=n["booltesttype"].startswith("IS_NOT"),
        is_true=n["booltesttype"].endswith("TRUE"),
        span=_build_span(n, c),
    )


def _build_null_test(n: Node, c: Context) -> pgast.NullTest:
    return pgast.NullTest(
        arg=_build_base_expr(n["arg"], c),
        negated=n["nulltesttype"] == "IS_NOT_NULL",
        span=_build_span(n, c),
    )


def _build_type_cast(n: Node, c: Context) -> pgast.TypeCast:
    return pgast.TypeCast(
        arg=_build_base_expr(n["arg"], c),
        type_name=_build_type_name(n["typeName"], c),
        span=_build_span(n, c),
    )


def _build_type_name(n: Node, c: Context) -> pgast.TypeName:
    n = _unwrap(n, "TypeName")

    name: tuple[str, ...] = tuple(_list(n, c, "names", _build_str))

    # we don't escape char properly, so let's just resolve it during parsing
    if name == ("char",):
        name = ("pg_catalog", "char")

    def unwrap_int_builder(n: Node, _c: Context) -> Node:
        return _unwrap_int(n)

    return pgast.TypeName(
        name=name,
        setof=_bool_or_false(n, "setof"),
        typmods=None,
        array_bounds=_maybe_list(n, c, "arrayBounds", unwrap_int_builder),
        span=_build_span(n, c),
    )


def _build_case_expr(n: Node, c: Context) -> pgast.CaseExpr:
    return pgast.CaseExpr(
        arg=_maybe(n, c, "arg", _build_base_expr),
        args=_list(n, c, "args", _build_case_when),
        defresult=_maybe(n, c, "defresult", _build_base_expr),
        span=_build_span(n, c),
    )


def _build_case_when(n: Node, c: Context) -> pgast.CaseWhen:
    n = _unwrap(n, "CaseWhen")
    return pgast.CaseWhen(
        expr=_build_base_expr(n["expr"], c),
        result=_build_base_expr(n["result"], c),
        span=_build_span(n, c),
    )


def _build_bool_expr(n: Node, c: Context) -> pgast.Expr:
    name = _build_str(n["boolop"], c)[0:-5]
    args = list(n["args"])
    res = pgast.Expr(
        name=name,
        lexpr=_build_base_expr(args.pop(0), c) if len(args) > 1 else None,
        rexpr=_build_base_expr(args.pop(0), c) if len(args) > 0 else None,
        span=_build_span(n, c),
    )
    while len(args) > 0:
        res = pgast.Expr(
            name=_build_str(n["boolop"], c)[0:-5],
            lexpr=res,
            rexpr=_build_base_expr(args.pop(0), c) if len(args) > 0 else None,
            span=_build_span(n, c),
        )
    return res


def _build_base_range_var(n: Node, c: Context) -> pgast.BaseRangeVar:
    return _enum(
        pgast.BaseRangeVar,
        n,
        c,
        {
            "RangeVar": _build_rel_range_var,
            "JoinExpr": _build_join_expr,
            "RangeFunction": _build_range_function,
            "RangeSubselect": _build_range_subselect,
        },
    )


def _build_const(n: Node, c: Context) -> pgast.BaseConstant:
    n = _unwrap(n, "val")
    span = _build_span(n, c)

    if "Null" in n or "isnull" in n:
        return pgast.NullConstant(span=span)

    if "Boolean" in n or "boolval" in n:
        return pgast.BooleanConstant(val=_unwrap_boolean(n), span=span)

    if "Integer" in n or "ival" in n:
        return pgast.NumericConstant(val=str(_unwrap_int(n)), span=span)

    if "Float" in n or "fval" in n:
        return pgast.NumericConstant(val=_unwrap_float(n), span=span)

    if "String" in n or "sval" in n:
        return pgast.StringConstant(val=_unwrap_string(n), span=span)
    if "BitString" in n or "bsval" in n:
        n = _unwrap(n, 'BitString')
        n = _unwrap(n, 'str')
        n = _unwrap(n, 'bsval')
        n = _unwrap(n, 'bsval')
        return pgast.BitStringConstant(kind=n[0], val=n[1:], span=span)
    raise PSqlUnsupportedError(n)


def _build_range_subselect(n: Node, c: Context) -> pgast.RangeSubselect:
    return pgast.RangeSubselect(
        alias=_maybe(n, c, "alias", _build_alias) or pgast.Alias(aliasname=""),
        lateral=_bool_or_false(n, "lateral"),
        subquery=_build_query(n["subquery"], c),
    )


def _build_range_function(n: Node, c: Context) -> pgast.RangeFunction:
    return pgast.RangeFunction(
        alias=_maybe(n, c, "alias", _build_alias) or pgast.Alias(aliasname=""),
        lateral=_bool_or_false(n, "lateral"),
        with_ordinality=_bool_or_false(n, "ordinality"),
        is_rowsfrom=_bool_or_false(n, "is_rowsfrom"),
        functions=[
            _build_base_expr(fn, c)
            for fn in n["functions"][0]["List"]["items"]
            if len(fn) > 0
        ],
    )


def _build_join_expr(n: Node, c: Context) -> pgast.JoinExpr:
    return pgast.JoinExpr(
        alias=_maybe(n, c, "alias", _build_alias) or pgast.Alias(aliasname=""),
        larg=_build_base_range_var(n["larg"], c),
        joins=[
            pgast.JoinClause(
                type=n["jointype"][5:],
                rarg=_build_base_range_var(n["rarg"], c),
                using_clause=_maybe_list(
                    n, c, "usingClause", _build_str, _as_column_ref
                ),
                quals=_maybe(n, c, "quals", _build_base_expr),
            )
        ],
    )


def _build_rel_range_var(n: Node, c: Context) -> pgast.RelRangeVar:
    return pgast.RelRangeVar(
        alias=_maybe(n, c, "alias", _build_alias) or pgast.Alias(aliasname=""),
        relation=_build_relation(n, c),
        include_inherited=_bool_or_false(n, "inh"),
        span=_build_span(n, c),
    )


def _build_alias(n: Node, c: Context) -> pgast.Alias:
    return pgast.Alias(
        aliasname=_build_str(n["aliasname"], c),
        colnames=_maybe_list(n, c, "colnames", _build_str),
    )


def _build_base_relation(n: Node, c: Context) -> pgast.BaseRelation:
    return _enum(
        pgast.BaseRelation,
        n,
        c,
        {
            "SelectStmt": _build_select_stmt,
            "Relation": _build_relation,
        },
    )


def _build_relation(n: Node, c: Context) -> pgast.Relation:
    return pgast.Relation(
        name=_maybe(n, c, "relname", _build_str),
        catalogname=_maybe(n, c, "catalogname", _build_str),
        schemaname=_maybe(n, c, "schemaname", _build_str),
        is_temporary=_maybe(n, c, "relpersistence", lambda n, _c: n == 't'),
        span=_build_span(n, c),
    )


def _build_implicit_row(n: Node, c: Context) -> pgast.ImplicitRowExpr:
    if isinstance(n, list):
        n = n[0]
    n = _unwrap(n, "List")

    return pgast.ImplicitRowExpr(
        args=[_build_base_expr(e, c) for e in n["items"] if len(e) > 0],
    )


def _build_array_expr(n: Node, c: Context) -> pgast.ArrayExpr:
    return pgast.ArrayExpr(elements=_list(n, c, "elements", _build_base_expr))


def _build_a_expr(n: Node, c: Context) -> pgast.BaseExpr:
    names: list[str] = _list(n, c, 'name', _build_str)
    if names[0] == 'pg_catalog':
        names.pop(0)
    name = names.pop(0)

    if n["kind"] == "AEXPR_OP":
        pass
    elif n["kind"] in ("AEXPR_LIKE", "AEXPR_ILIKE"):
        op = name
        if op.endswith("*"):
            name = "ILIKE"
        else:
            name = "LIKE"
        if op.startswith("!"):
            name = "NOT " + name
    elif n["kind"] == "AEXPR_IN":
        if name == "<>":
            name = "NOT IN"
        else:
            name = "IN"
    elif n["kind"] in ("AEXPR_OP_ANY", "AEXPR_OP_ALL"):
        operator = "ANY" if n["kind"] == "AEXPR_OP_ANY" else "ALL"

        return pgast.SubLink(
            operator=name + " " + operator,
            test_expr=_maybe(n, c, "lexpr", _build_base_expr),
            expr=_build_base_expr(n["rexpr"], c),
            span=_build_span(n, c),
        )
    elif n['kind'] == 'AEXPR_NULLIF':
        return pgast.FuncCall(
            name=('nullif',),
            args=[
                _build_base_expr(n['lexpr'], c),
                _build_base_expr(n['rexpr'], c),
            ],
        )
    elif n['kind'] == 'AEXPR_DISTINCT':
        name = 'IS DISTINCT FROM'
    elif n['kind'] == 'AEXPR_NOT_DISTINCT':
        name = 'IS NOT DISTINCT FROM'
    else:
        raise PSqlUnsupportedError(n)

    return pgast.Expr(
        name=name,
        lexpr=_maybe(n, c, "lexpr", _build_base_expr),
        rexpr=_maybe(n, c, "rexpr", _build_base_expr),
        span=_build_span(n, c),
    )


def _build_func_call(n: Node, c: Context) -> pgast.FuncCall:
    n = _unwrap(n, "FuncCall")

    return pgast.FuncCall(
        name=tuple(_list(n, c, "funcname", _build_str)),
        args=_maybe_list(n, c, "args", _build_base_expr) or [],
        agg_order=_maybe_list(n, c, "aggOrder", _build_sort_by),
        agg_filter=_maybe(n, c, "aggFilter", _build_base_expr),
        agg_star=_bool_or_false(n, "agg_star"),
        agg_distinct=_bool_or_false(n, "agg_distinct"),
        over=_maybe(n, c, "over", _build_window_def),
        with_ordinality=_bool_or_false(n, "withOrdinality"),
        span=_build_span(n, c),
    )


def _build_coalesce(n: Node, c: Context) -> pgast.CoalesceExpr:
    return pgast.CoalesceExpr(
        args=_list(n, c, "args", _build_base_expr),
    )


def _build_index_or_slice(n: Node, c: Context) -> pgast.Slice | pgast.Index:
    if 'is_slice' in n and n['is_slice']:
        return pgast.Slice(
            lidx=_build_base_expr(n['lidx'], c),
            ridx=_build_base_expr(n['uidx'], c),
        )
    else:
        idx = n['lidx'] if 'lidx' in n else n['uidx']
        return pgast.Index(
            idx=_build_base_expr(idx, c),
        )


def _build_res_target(n: Node, c: Context) -> pgast.ResTarget:
    n = _unwrap(n, "ResTarget")
    return pgast.ResTarget(
        name=_maybe(n, c, "name", _build_str),
        val=_build_base_expr(n["val"], c),
        span=_build_span(n, c),
    )


def _build_insert_target(n: Node, c: Context) -> pgast.InsertTarget:
    n = _unwrap(n, "ResTarget")
    return pgast.InsertTarget(
        name=_build_str(n['name'], c),
        span=_build_span(n, c),
    )


def _build_update_targets(
    target_list: list[Node], c: Context
) -> list[pgast.UpdateTarget | pgast.MultiAssignRef]:
    targets: list[pgast.UpdateTarget | pgast.MultiAssignRef] = []
    while len(target_list) > 0:
        val: dict = target_list[0]["ResTarget"]["val"]
        if first_mar := val.get("MultiAssignRef", None):
            ncolumns = first_mar['ncolumns']

            columns: list[str] = []
            for _ in range(ncolumns):
                target = target_list.pop(0)
                mar = target['ResTarget']

                if 'indirection' in mar:
                    raise PSqlUnsupportedError(
                        val, f"multi-assign SET with indirection"
                    )

                columns.append(mar['name'])

            targets.append(_build_multi_assign_ref(first_mar, columns, c))
        else:
            target = target_list.pop(0)
            targets.append(_build_update_target(target, c))

    return targets


def _build_multi_assign_ref(
    n: Node, columns: list[str], c: Context
) -> pgast.MultiAssignRef:
    return pgast.MultiAssignRef(
        source=_build_base_expr(n['source'], c),
        columns=columns,
        span=_build_span(n, c),
    )


def _build_update_target(
    n: Node, c: Context
) -> pgast.UpdateTarget | pgast.MultiAssignRef:
    n = _unwrap(n, "ResTarget")
    return pgast.UpdateTarget(
        name=_build_str(n['name'], c),
        val=_build_base_expr(n['val'], c),
        indirection=_maybe_list(n, c, "indirection", _build_indirection_op),
        span=_build_span(n, c),
    )


def _build_window_def(n: Node, c: Context) -> pgast.WindowDef:
    return pgast.WindowDef(
        name=_maybe(n, c, "name", _build_str),
        refname=_maybe(n, c, "refname", _build_str),
        partition_clause=_maybe_list(n, c, "partitionClause", _build_base_expr),
        order_clause=_maybe_list(n, c, "orderClause", _build_sort_by),
        frame_options=None,
        start_offset=_maybe(n, c, "startOffset", _build_base_expr),
        end_offset=_maybe(n, c, "endOffset", _build_base_expr),
        span=_build_span(n, c),
    )


def _build_sort_by(n: Node, c: Context) -> pgast.SortBy:
    n = _unwrap(n, "SortBy")
    return pgast.SortBy(
        node=_build_base_expr(n["node"], c),
        dir=_maybe(n, c, "sortby_dir", _build_sort_order),
        nulls=_maybe(n, c, "sortby_nulls", _build_nones_order),
        span=_build_span(n, c),
    )


def _build_locking_clause(n: Node, c: Context) -> pgast.LockingClause:
    n = _unwrap(n, "LockingClause")

    match n["strength"]:
        case "LCS_FORUPDATE":
            strength = pgast.LockClauseStrength.UPDATE
        case "LCS_FORNOKEYUPDATE":
            strength = pgast.LockClauseStrength.NO_KEY_UPDATE
        case "LCS_FORSHARE":
            strength = pgast.LockClauseStrength.SHARE
        case "LCS_FORKEYSHARE":
            strength = pgast.LockClauseStrength.KEY_SHARE
        case lcs:
            raise PSqlUnsupportedError(n, f"FOR lock strength: {lcs}")

    if pol := n.get("waitPolicy"):
        wait_policy = getattr(pgast.LockWaitPolicy, pol, None)
        if wait_policy is None:
            raise PSqlUnsupportedError(n, f"FOR wait policy: {pol}")
    else:
        wait_policy = None

    return pgast.LockingClause(
        strength=strength,
        locked_rels=_maybe_list(
            n, c, "lockedRels", _build_rel_range_var, unwrap="RangeVar"
        ),
        wait_policy=wait_policy,
    )


def _build_nones_order(n: Node, _c: Context) -> Optional[qlast.NonesOrder]:
    if n == "SORTBY_NULLS_FIRST":
        return qlast.NonesFirst
    if n == "SORTBY_NULLS_LAST":
        return qlast.NonesLast
    return None


def _build_sort_order(n: Node, _c: Context) -> Optional[qlast.SortOrder]:
    if n == "SORTBY_DESC":
        return qlast.SortOrder.Desc
    if n == "SORTBY_ASC":
        return qlast.SortOrder.Asc
    if n == "SORTBY_DEFAULT":
        return None
    raise PSqlUnsupportedError(n)


def _build_column_ref(n: Node, c: Context) -> pgast.ColumnRef:
    return pgast.ColumnRef(
        name=_list(n, c, "fields", _build_string_or_star),
        optional=_maybe(n, c, "optional", _build_bool),
        span=_build_span(n, c),
    )


def _build_on_conflict(n: Node, c: Context) -> pgast.OnConflictClause:
    action_str = _build_str(n["action"], c)
    if action_str == "ONCONFLICT_NOTHING":
        action = pgast.OnConflictAction.DO_NOTHING
    elif action_str == "ONCONFLICT_UPDATE":
        action = pgast.OnConflictAction.DO_UPDATE
    else:
        raise PSqlUnsupportedError(n, f"ON CONFLICT {action_str}")

    return pgast.OnConflictClause(
        action=action,
        target=_maybe(n, c, "infer", _build_on_conflict_target),
        update_list=_maybe(n, c, "targetList", _build_update_targets) or [],
        update_where=_maybe(n, c, "whereClause", _build_base_expr),
        span=_build_span(n, c),
    )


def _build_on_conflict_target(n: Node, c: Context) -> pgast.OnConflictTarget:
    return pgast.OnConflictTarget(
        index_elems=_maybe_list(n, c, "indexElems", _build_index_elem),
        index_where=_maybe(n, c, "whereClause", _build_base_expr),
        constraint_name=_maybe(n, c, "conname", _build_str),
        span=_build_span(n, c),
    )


def _build_index_elem(n: Node, c: Context) -> pgast.IndexElem:
    n = _unwrap(n, 'IndexElem')

    expr: pgast.BaseExpr
    if 'name' in n:
        expr = pgast.ColumnRef(name=(n['name'],))
    elif 'indexcolname' in n:
        expr = pgast.ColumnRef(name=(n['name'],))
    elif 'expr' in n:
        expr = _build_base_expr(n['expr'], c)
    else:
        raise PSqlUnsupportedError(n)

    # TODO:
    # collation
    # opclass
    # opclassopts

    return pgast.IndexElem(
        expr=expr,
        ordering=_build_sort_order(n['ordering'], c),
        nulls_ordering=_build_nones_order(n['nulls_ordering'], c),
        span=_build_span(n, c),
    )


def _build_star(_n: Node, _c: Context) -> pgast.Star | str:
    return pgast.Star()


def _build_string_or_star(node: Node, c: Context) -> pgast.Star | str:
    return _enum(
        pgast.Star | str,  # type: ignore
        node,
        c,
        {"String": _build_str, "A_Star": _build_star},
    )


def _build_copy_format(n: Node, c: Context) -> pgast.CopyFormat:
    val = _build_str(n, c)
    if val == 'text':
        return pgast.CopyFormat.TEXT
    if val == 'csv':
        return pgast.CopyFormat.CSV
    if val == 'binary':
        return pgast.CopyFormat.BINARY
    raise PSqlUnsupportedError(val, f"{val} format")


def _build_copy_options(nodes: list[Node], c: Context) -> pgast.CopyOptions:
    opt = pgast.CopyOptions()
    for n in nodes:
        if 'DefElem' not in n or 'defname' not in n['DefElem']:
            continue
        n = n['DefElem']
        def_name = n['defname']
        arg = n['arg'] if 'arg' in n else None

        if def_name == 'format' and arg:
            opt.format = _build_copy_format(arg, c)

        elif def_name == 'freeze':
            opt.freeze = _build_str(arg, c) == 'true' if arg else True

        elif def_name == 'delimiter' and arg:
            opt.delimiter = _build_str(arg, c)

        elif def_name == 'null' and arg:
            opt.null = _build_str(arg, c)

        elif def_name == 'header' and arg:
            opt.header = _build_str(arg, c) == 'true' if arg else True

        elif def_name == 'quote' and arg:
            opt.quote = _build_str(arg, c)

        elif def_name == 'escape' and arg:
            opt.escape = _build_str(arg, c)

        elif def_name == 'force_quote':
            arg = _unwrap(arg, 'List')
            opt.force_quote = _list(arg, c, 'items', _build_str)

        elif def_name == 'force_not_null':
            arg = _unwrap(arg, 'List')
            opt.force_not_null = _list(arg, c, 'items', _build_str)

        elif def_name == 'force_null':
            arg = _unwrap(arg, 'List')
            opt.force_null = _list(arg, c, 'items', _build_str)

        elif def_name == 'encoding':
            opt.encoding = _build_str(arg, c)
    return opt


def _build_copy(n: Node, c: Context) -> pgast.CopyStmt:
    return pgast.CopyStmt(
        relation=_maybe(n, c, 'relation', _build_relation),
        colnames=_maybe_list(n, c, 'attlist', _build_str),
        query=_maybe(n, c, 'query', _build_query),
        is_from=_bool_or_false(n, 'is_from'),
        is_program=_bool_or_false(n, 'is_program'),
        filename=_maybe(n, c, 'filename', _build_str),
        options=(
            _maybe(n, c, 'options', _build_copy_options) or pgast.CopyOptions()
        ),
        where_clause=_maybe(n, c, "whereClause", _build_base_expr),
        span=_build_span(n, c),
    )
