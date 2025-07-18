#
# This source file is part of the EdgeDB open source project.
#
# Copyright 2019-present MagicStack Inc. and the EdgeDB authors.
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


from __future__ import annotations

from edb.edgeql import ast as qlast

from edb.common import parsing
from edb import errors

from . import expressions
from . import commondl

from .precedence import *  # NOQA
from .tokens import *  # NOQA
from .commondl import *  # NOQA


Nonterm = expressions.Nonterm  # type: ignore[misc]
OptSemicolons = commondl.OptSemicolons  # type: ignore[misc]


sdl_nontem_helper = commondl.NewNontermHelper(__name__)
_new_nonterm = sdl_nontem_helper._new_nonterm


# top-level SDL statements
class SDLStatement(Nonterm):
    @parsing.inline(0)
    def reduce_SDLBlockStatement(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_SDLShortStatement_SEMICOLON(self, *kids):
        pass


# a list of SDL statements with optional semicolon separators
class SDLStatements(parsing.ListNonterm, element=SDLStatement,
                    separator=OptSemicolons):
    pass


# These statements have a block
class SDLBlockStatement(Nonterm):
    @parsing.inline(0)
    def reduce_ModuleDeclaration(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_ScalarTypeDeclaration(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_AnnotationDeclaration(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_ObjectTypeDeclaration(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_AliasDeclaration(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_ConstraintDeclaration(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_LinkDeclaration(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_PropertyDeclaration(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_FunctionDeclaration(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_GlobalDeclaration(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_IndexDeclaration(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_PermissionDeclaration(self, *kids):
        pass


# these statements have no {} block
class SDLShortStatement(Nonterm):

    @parsing.inline(0)
    def reduce_ExtensionRequirementDeclaration(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_FutureRequirementDeclaration(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_ScalarTypeDeclarationShort(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_AnnotationDeclarationShort(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_ObjectTypeDeclarationShort(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_AliasDeclarationShort(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_ConstraintDeclarationShort(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_LinkDeclarationShort(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_PropertyDeclarationShort(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_FunctionDeclarationShort(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_GlobalDeclarationShort(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_IndexDeclarationShort(self, *kids):
        pass

    @parsing.inline(0)
    def reduce_PermissionDeclarationShort(self, *kids):
        pass


# A rule for an SDL block, either as part of `module` declaration or
# as top-level schema used in MIGRATION DDL.
class SDLCommandBlock(Nonterm):
    # this command block can be empty
    def reduce_LBRACE_OptSemicolons_RBRACE(self, *kids):
        self.val = []

    def reduce_statement_without_semicolons(self, _0, _1, stmt, _2):
        r"""%reduce LBRACE \
                OptSemicolons SDLShortStatement \
            RBRACE
        """
        self.val = [stmt.val]

    def reduce_statements_without_optional_trailing_semicolons(self, *kids):
        r"""%reduce LBRACE \
                OptSemicolons SDLStatements \
                OptSemicolons SDLShortStatement \
            RBRACE
        """
        _, _, stmts, _, stmt, _ = kids
        self.val = stmts.val + [stmt.val]

    @parsing.inline(2)
    def reduce_LBRACE_OptSemicolons_SDLStatements_RBRACE(self, *kids):
        pass

    @parsing.inline(2)
    def reduce_statements_without_optional_trailing_semicolons2(self, *kids):
        r"""%reduce LBRACE \
                OptSemicolons SDLStatements \
                Semicolons \
            RBRACE
        """


class SDLProductionHelper:
    def _passthrough(self, *cmds):
        self.val = cmds[0].val

    def _singleton_list(self, cmd):
        self.val = [cmd.val]

    def _empty(self, *kids):
        self.val = []

    def _block(self, lbrace, sc1, cmdl, rbrace):
        self.val = [cmdl.val]

    def _block2(self, lbrace, sc1, cmdlist, sc2, rbrace):
        self.val = cmdlist.val

    def _block3(self, lbrace, sc1, cmdlist, sc2, cmd, rbrace):
        self.val = cmdlist.val + [cmd.val]


def sdl_commands_block(parent, *commands, opt=True):
    if parent is None:
        parent = ''

    # SDLCommand := SDLCommand1 | SDLCommand2 ...
    #
    # All the "short" commands, ones that need a ";" are gathered as
    # SDLCommandShort.
    #
    # All the "block" commands, ones that have a "{...}" and don't
    # need a ";" are gathered as SDLCommandBlock.
    clsdict_b = {}
    clsdict_s = {}

    for command in commands:
        if command.__name__.endswith('Block'):
            clsdict_b[f'reduce_{command.__name__}'] = \
                SDLProductionHelper._passthrough
        else:
            clsdict_s[f'reduce_{command.__name__}'] = \
                SDLProductionHelper._passthrough

    cmd_s = _new_nonterm(f'{parent}SDLCommandShort', clsdict=clsdict_s)
    cmd_b = _new_nonterm(f'{parent}SDLCommandBlock', clsdict=clsdict_b)

    # Merged command which has minimal ";"
    #
    # SDLCommandFull := SDLCommandShort ; | SDLCommandBlock
    clsdict = {}
    clsdict[f'reduce_{cmd_s.__name__}_SEMICOLON'] = \
        SDLProductionHelper._passthrough
    clsdict[f'reduce_{cmd_b.__name__}'] = \
        SDLProductionHelper._passthrough
    cmd = _new_nonterm(f'{parent}SDLCommandFull', clsdict=clsdict)

    # SDLCommandsList := SDLCommandFull [; SDLCommandFull ...]
    cmdlist = _new_nonterm(f'{parent}SDLCommandsList',
                           clsbases=(parsing.ListNonterm,),
                           clskwds=dict(element=cmd, separator=OptSemicolons))

    # Command block is tricky, but the inner commands must terminate
    # without a ";", is possible.
    #
    # SDLCommandsBlock :=
    #
    #   { [ ; ] SDLCommandFull }
    #   { [ ; ] SDLCommandsList [ ; ]} |
    #   { [ ; ] SDLCommandsList [ ; ] SDLCommandFull }
    clsdict = {}
    clsdict[f'reduce_LBRACE_OptSemicolons_{cmd_s.__name__}_RBRACE'] = \
        SDLProductionHelper._block
    clsdict[f'reduce_LBRACE_OptSemicolons_{cmdlist.__name__}_' +
            f'OptSemicolons_RBRACE'] = \
        SDLProductionHelper._block2
    clsdict[f'reduce_LBRACE_OptSemicolons_{cmdlist.__name__}_OptSemicolons_' +
            f'{cmd_s.__name__}_RBRACE'] = \
        SDLProductionHelper._block3
    clsdict[f'reduce_LBRACE_OptSemicolons_RBRACE'] = \
        SDLProductionHelper._empty
    _new_nonterm(f'{parent}SDLCommandsBlock', clsdict=clsdict)

    if opt is False:
        #   | Command
        clsdict = {}
        clsdict[f'reduce_{cmd_s.__name__}'] = \
            SDLProductionHelper._singleton_list
        clsdict[f'reduce_{cmd_b.__name__}'] = \
            SDLProductionHelper._singleton_list
        _new_nonterm(parent + 'SingleSDLCommandBlock', clsdict=clsdict)


class Using(Nonterm):
    def reduce_USING_ParenExpr(self, *kids):
        _, paren_expr = kids
        self.val = qlast.SetField(
            name='expr',
            value=paren_expr.val,
            special_syntax=True,
        )


class SetField(Nonterm):
    # field := <expr>
    def reduce_Identifier_ASSIGN_GenExpr(self, *kids):
        identifier, _, expr = kids
        self.val = qlast.SetField(name=identifier.val, value=expr.val)


class SetAnnotation(Nonterm):
    def reduce_ANNOTATION_NodeName_ASSIGN_GenExpr(self, *kids):
        _, name, _, expr = kids
        self.val = qlast.CreateAnnotationValue(name=name.val, value=expr.val)


sdl_commands_block(
    'Create',
    Using,
    SetField,
    SetAnnotation)


class ExtensionRequirementDeclaration(Nonterm):

    def reduce_USING_EXTENSION_ShortNodeName_OptExtensionVersion(self, *kids):
        _, _, name, version = kids
        self.val = qlast.CreateExtension(
            name=name.val,
            version=version.val,
        )


class FutureRequirementDeclaration(Nonterm):

    def reduce_USING_FUTURE_ShortNodeName(self, *kids):
        _, _, name = kids
        self.val = qlast.CreateFuture(
            name=name.val,
        )


class ModuleDeclaration(Nonterm):
    def reduce_MODULE_ModuleName_SDLCommandBlock(self, _, name, block):

        # Check that top-level declarations DO NOT use fully-qualified
        # names and aren't nested module blocks.
        declarations = block.val
        for decl in declarations:
            if isinstance(decl, qlast.ExtensionCommand):
                raise errors.EdgeQLSyntaxError(
                    "'using extension' cannot be used inside a module block",
                    span=decl.span)
            elif isinstance(decl, qlast.FutureCommand):
                raise errors.EdgeQLSyntaxError(
                    "'using future' cannot be used inside a module block",
                    span=decl.span)
            elif decl.name.module is not None:
                raise errors.EdgeQLSyntaxError(
                    "fully-qualified name is not allowed in "
                    "a module declaration",
                    span=decl.name.span)

        self.val = qlast.ModuleDeclaration(
            # mirror what we do in CREATE MODULE
            name=qlast.ObjectRef(
                module=None, name='::'.join(name.val), span=name.span
            ),
            declarations=declarations,
        )


#
# Constraints
#
class ConstraintDeclaration(Nonterm):
    def reduce_CreateConstraint(self, *kids):
        r"""%reduce ABSTRACT CONSTRAINT NodeName OptOnExpr \
                    OptExtendingSimple CreateSDLCommandsBlock"""
        _, _, name, on_expr, extending, commands = kids
        self.val = qlast.CreateConstraint(
            name=name.val,
            subjectexpr=on_expr.val,
            bases=extending.val,
            commands=commands.val,
        )

    def reduce_CreateConstraint_CreateFunctionArgs(self, *kids):
        r"""%reduce ABSTRACT CONSTRAINT NodeName CreateFunctionArgs \
                    OptOnExpr OptExtendingSimple CreateSDLCommandsBlock"""
        _, _, name, args, on_expr, extending, commands = kids
        self.val = qlast.CreateConstraint(
            name=name.val,
            params=args.val,
            subjectexpr=on_expr.val,
            bases=extending.val,
            commands=commands.val,
        )


class ConstraintDeclarationShort(Nonterm):
    def reduce_CreateConstraint(self, *kids):
        r"""%reduce ABSTRACT CONSTRAINT NodeName OptOnExpr \
                    OptExtendingSimple"""
        _, _, name, on_expr, extending = kids
        self.val = qlast.CreateConstraint(
            name=name.val,
            subject=on_expr.val,
            bases=extending.val,
        )

    def reduce_CreateConstraint_CreateFunctionArgs(self, *kids):
        r"""%reduce ABSTRACT CONSTRAINT NodeName CreateFunctionArgs \
                    OptOnExpr OptExtendingSimple"""
        _, _, name, args, on_expr, extending = kids
        self.val = qlast.CreateConstraint(
            name=name.val,
            params=args.val,
            subject=on_expr.val,
            bases=extending.val,
        )


class ConcreteConstraintBlock(Nonterm):
    def reduce_CreateConstraint(self, *kids):
        r"""%reduce CONSTRAINT \
                    NodeName OptConcreteConstraintArgList OptOnExpr \
                    OptExceptExpr \
                    CreateSDLCommandsBlock"""
        _, name, arg_list, on_expr, except_expr, commands = kids
        self.val = qlast.CreateConcreteConstraint(
            name=name.val,
            args=arg_list.val,
            subjectexpr=on_expr.val,
            except_expr=except_expr.val,
            commands=commands.val,
        )

    def reduce_CreateDelegatedConstraint(self, *kids):
        r"""%reduce DELEGATED CONSTRAINT \
                    NodeName OptConcreteConstraintArgList OptOnExpr \
                    OptExceptExpr \
                    CreateSDLCommandsBlock"""
        _, _, name, arg_list, on_expr, except_expr, commands = kids
        self.val = qlast.CreateConcreteConstraint(
            delegated=True,
            name=name.val,
            args=arg_list.val,
            subjectexpr=on_expr.val,
            except_expr=except_expr.val,
            commands=commands.val,
        )


class ConcreteConstraintShort(Nonterm):
    def reduce_CreateConstraint(self, *kids):
        r"""%reduce CONSTRAINT \
                    NodeName OptConcreteConstraintArgList OptOnExpr \
                    OptExceptExpr"""
        _, name, arg_list, on_expr, except_expr = kids
        self.val = qlast.CreateConcreteConstraint(
            name=name.val,
            args=arg_list.val,
            subjectexpr=on_expr.val,
            except_expr=except_expr.val,
        )

    def reduce_CreateDelegatedConstraint(self, *kids):
        r"""%reduce DELEGATED CONSTRAINT \
                    NodeName OptConcreteConstraintArgList OptOnExpr \
                    OptExceptExpr"""
        _, _, name, arg_list, on_expr, except_expr = kids
        self.val = qlast.CreateConcreteConstraint(
            delegated=True,
            name=name.val,
            args=arg_list.val,
            subjectexpr=on_expr.val,
            except_expr=except_expr.val,
        )


#
# Scalar Types
#

sdl_commands_block(
    'CreateScalarType',
    SetField,
    SetAnnotation,
    ConcreteConstraintBlock,
    ConcreteConstraintShort,
)


class ScalarTypeDeclaration(Nonterm):
    def reduce_CreateAbstractScalarTypeStmt(self, *kids):
        r"""%reduce \
            ABSTRACT SCALAR TYPE NodeName \
            OptExtending CreateScalarTypeSDLCommandsBlock \
        """
        _, _, _, name, extending, commands = kids
        self.val = qlast.CreateScalarType(
            abstract=True,
            name=name.val,
            bases=extending.val,
            commands=commands.val,
        )

    def reduce_ScalarTypeDeclaration(self, *kids):
        r"""%reduce \
            SCALAR TYPE NodeName \
            OptExtending CreateScalarTypeSDLCommandsBlock \
        """
        _, _, name, extending, commands = kids
        self.val = qlast.CreateScalarType(
            name=name.val,
            bases=extending.val,
            commands=commands.val,
        )


class ScalarTypeDeclarationShort(Nonterm):
    def reduce_CreateAbstractScalarTypeStmt(self, *kids):
        r"""%reduce \
            ABSTRACT SCALAR TYPE NodeName \
            OptExtending \
        """
        _, _, _, name, extending = kids
        self.val = qlast.CreateScalarType(
            abstract=True,
            name=name.val,
            bases=extending.val,
        )

    def reduce_ScalarTypeDeclaration(self, *kids):
        r"""%reduce \
            SCALAR TYPE NodeName \
            OptExtending \
        """
        _, _, name, extending = kids
        self.val = qlast.CreateScalarType(
            name=name.val,
            bases=extending.val,
        )


#
# Annotations
#
class AnnotationDeclaration(Nonterm):
    def reduce_CreateAnnotation(self, *kids):
        r"""%reduce ABSTRACT ANNOTATION NodeName OptExtendingSimple \
                    CreateSDLCommandsBlock"""
        _, _, name, extending, commands = kids
        self.val = qlast.CreateAnnotation(
            abstract=True,
            name=name.val,
            bases=extending.val,
            inheritable=False,
            commands=commands.val,
        )

    def reduce_CreateInheritableAnnotation(self, *kids):
        r"""%reduce ABSTRACT INHERITABLE ANNOTATION
                    NodeName OptExtendingSimple CreateSDLCommandsBlock"""
        _, _, _, name, extending, commands = kids
        self.val = qlast.CreateAnnotation(
            abstract=True,
            name=name.val,
            bases=extending.val,
            inheritable=True,
            commands=commands.val,
        )


class AnnotationDeclarationShort(Nonterm):
    def reduce_CreateAnnotation(self, *kids):
        r"""%reduce ABSTRACT ANNOTATION NodeName OptExtendingSimple"""
        _, _, name, extending = kids
        self.val = qlast.CreateAnnotation(
            abstract=True,
            name=name.val,
            bases=extending.val,
            inheritable=False,
        )

    def reduce_CreateInheritableAnnotation(self, *kids):
        r"""%reduce ABSTRACT INHERITABLE ANNOTATION
                    NodeName OptExtendingSimple"""
        _, _, _, name, extending = kids
        self.val = qlast.CreateAnnotation(
            abstract=True,
            name=name.val,
            bases=extending.val,
            inheritable=True,
        )


#
# Indexes
#
sdl_commands_block(
    'CreateIndex',
    Using,
    SetField,
    SetAnnotation,
)


class IndexDeclaration(
    Nonterm,
    commondl.ProcessIndexMixin,
):
    def reduce_CreateIndex(self, *kids):
        r"""%reduce ABSTRACT INDEX NodeName \
                    OptExtendingSimple CreateIndexSDLCommandsBlock"""
        _, _, name, bases, commands = kids
        self.val = qlast.CreateIndex(
            name=name.val,
            bases=bases.val,
            commands=commands.val,
        )

    def reduce_CreateIndex_CreateFunctionArgs(self, *kids):
        r"""%reduce ABSTRACT INDEX NodeName IndexExtArgList \
                    OptExtendingSimple CreateIndexSDLCommandsBlock"""
        _, _, name, arg_list, bases, commands = kids
        params, kwargs = self._process_params_or_kwargs(
            bases.val, arg_list.val)
        self.val = qlast.CreateIndex(
            name=name.val,
            params=params,
            kwargs=kwargs,
            bases=bases.val,
            commands=commands.val,
        )


class IndexDeclarationShort(
    Nonterm,
    commondl.ProcessIndexMixin,
):
    def reduce_CreateIndex(self, *kids):
        r"""%reduce ABSTRACT INDEX NodeName OptExtendingSimple"""
        _, _, name, bases = kids
        self.val = qlast.CreateIndex(
            name=name.val,
            bases=bases.val,
        )

    def reduce_CreateIndex_CreateFunctionArgs(self, *kids):
        r"""%reduce ABSTRACT INDEX NodeName IndexExtArgList \
                    OptExtendingSimple"""
        _, _, name, arg_list, bases = kids
        params, kwargs = self._process_params_or_kwargs(
            bases.val, arg_list.val)
        self.val = qlast.CreateIndex(
            name=name.val,
            params=params,
            kwargs=kwargs,
            bases=bases.val,
        )


sdl_commands_block(
    'CreateConcreteIndex',
    SetField,
    SetAnnotation)


class ConcreteIndexDeclarationBlock(Nonterm, commondl.ProcessIndexMixin):
    def reduce_CreateConcreteAnonymousIndex(self, *kids):
        r"""%reduce INDEX OnExpr OptExceptExpr
                    CreateConcreteIndexSDLCommandsBlock
        """
        _, on_expr, except_expr, commands = kids
        self.val = qlast.CreateConcreteIndex(
            name=qlast.ObjectRef(module='__', name='idx', span=kids[0].span),
            expr=on_expr.val,
            except_expr=except_expr.val,
            commands=commands.val,
        )

    def reduce_CreateConcreteAnonymousDeferredIndex(self, *kids):
        r"""%reduce DEFERRED INDEX OnExpr OptExceptExpr
                    CreateConcreteIndexSDLCommandsBlock
        """
        _, _, on_expr, except_expr, commands = kids
        self.val = qlast.CreateConcreteIndex(
            name=qlast.ObjectRef(module='__', name='idx', span=kids[0].span),
            expr=on_expr.val,
            except_expr=except_expr.val,
            deferred=True,
            commands=commands.val,
        )

    def reduce_CreateConcreteIndex(self, *kids):
        r"""%reduce INDEX NodeName \
                    OnExpr OptExceptExpr \
                    CreateConcreteIndexSDLCommandsBlock \
        """
        _, name, on_expr, except_expr, commands = kids
        self.val = qlast.CreateConcreteIndex(
            name=name.val,
            expr=on_expr.val,
            except_expr=except_expr.val,
            commands=commands.val,
        )

    def reduce_CreateConcreteDeferredIndex(self, *kids):
        r"""%reduce DEFERRED INDEX NodeName \
                    OnExpr OptExceptExpr \
                    CreateConcreteIndexSDLCommandsBlock \
        """
        _, _, name, on_expr, except_expr, commands = kids
        self.val = qlast.CreateConcreteIndex(
            name=name.val,
            expr=on_expr.val,
            except_expr=except_expr.val,
            deferred=True,
            commands=commands.val,
        )

    def reduce_CreateConcreteIndexWithArgs(self, *kids):
        r"""%reduce INDEX NodeName IndexExtArgList \
                    OnExpr OptExceptExpr \
                    CreateConcreteIndexSDLCommandsBlock \
        """
        _, name, arg_list, on_expr, except_expr, commands = kids
        kwargs = self._process_arguments(arg_list.val)
        self.val = qlast.CreateConcreteIndex(
            name=name.val,
            kwargs=kwargs,
            expr=on_expr.val,
            except_expr=except_expr.val,
            commands=commands.val,
        )

    def reduce_CreateConcreteDeferredIndexWithArgs(self, *kids):
        r"""%reduce DEFERRED INDEX NodeName IndexExtArgList \
                    OnExpr OptExceptExpr \
                    CreateConcreteIndexSDLCommandsBlock \
        """
        _, _, name, arg_list, on_expr, except_expr, commands = kids
        kwargs = self._process_arguments(arg_list.val)
        self.val = qlast.CreateConcreteIndex(
            name=name.val,
            kwargs=kwargs,
            expr=on_expr.val,
            except_expr=except_expr.val,
            deferred=True,
            commands=commands.val,
        )


class ConcreteIndexDeclarationShort(Nonterm, commondl.ProcessIndexMixin):
    def reduce_INDEX_OnExpr_OptExceptExpr(self, *kids):
        _, on_expr, except_expr = kids
        self.val = qlast.CreateConcreteIndex(
            name=qlast.ObjectRef(module='__', name='idx', span=kids[0].span),
            expr=on_expr.val,
            except_expr=except_expr.val,
        )

    def reduce_DEFERRED_INDEX_OnExpr_OptExceptExpr(self, *kids):
        _, _, on_expr, except_expr = kids
        self.val = qlast.CreateConcreteIndex(
            name=qlast.ObjectRef(module='__', name='idx', span=kids[0].span),
            expr=on_expr.val,
            except_expr=except_expr.val,
            deferred=True,
        )

    def reduce_CreateConcreteIndex(self, *kids):
        r"""%reduce INDEX NodeName OnExpr OptExceptExpr
        """
        _, name, on_expr, except_expr = kids
        self.val = qlast.CreateConcreteIndex(
            name=name.val,
            expr=on_expr.val,
            except_expr=except_expr.val,
        )

    def reduce_CreateConcreteDeferredIndex(self, *kids):
        r"""%reduce DEFERRED INDEX NodeName OnExpr OptExceptExpr
        """
        _, _, name, on_expr, except_expr = kids
        self.val = qlast.CreateConcreteIndex(
            name=name.val,
            expr=on_expr.val,
            except_expr=except_expr.val,
            deferred=True,
        )

    def reduce_CreateConcreteIndexWithArgs(self, *kids):
        r"""%reduce INDEX NodeName IndexExtArgList \
                    OnExpr OptExceptExpr \
        """
        _, name, arg_list, on_expr, except_expr = kids
        kwargs = self._process_arguments(arg_list.val)
        self.val = qlast.CreateConcreteIndex(
            name=name.val,
            kwargs=kwargs,
            expr=on_expr.val,
            except_expr=except_expr.val,
        )

    def reduce_CreateConcreteDeferredIndexWithArgs(self, *kids):
        r"""%reduce DEFERRED INDEX NodeName IndexExtArgList
                    OnExpr OptExceptExpr
        """
        _, _, name, arg_list, on_expr, except_expr = kids
        kwargs = self._process_arguments(arg_list.val)
        self.val = qlast.CreateConcreteIndex(
            name=name.val,
            kwargs=kwargs,
            expr=on_expr.val,
            except_expr=except_expr.val,
            deferred=True,
        )


#
# Mutation rewrites
#
sdl_commands_block(
    'CreateRewrite',
    SetField,
    SetAnnotation
)


class RewriteDeclarationBlock(Nonterm):
    def reduce_CreateRewrite(self, _r, kinds, _u, expr, commands):
        """%reduce
            REWRITE RewriteKindList
            USING ParenExpr
            CreateRewriteSDLCommandsBlock
        """
        # The name isn't important (it gets replaced) but we need to
        # have one.
        name = '/'.join(str(kind) for kind in kinds.val)
        self.val = qlast.CreateRewrite(
            name=qlast.ObjectRef(name=name, span=kinds.span),
            kinds=kinds.val,
            expr=expr.val,
            commands=commands.val,
        )


class RewriteDeclarationShort(Nonterm):
    def reduce_CreateRewrite(self, _r, kinds, _u, expr):
        """%reduce
            REWRITE RewriteKindList
            USING ParenExpr
        """
        # The name isn't important (it gets replaced) but we need to
        # have one.
        name = '/'.join(str(kind) for kind in kinds.val)
        self.val = qlast.CreateRewrite(
            name=qlast.ObjectRef(name=name, span=kinds.span),
            kinds=kinds.val,
            expr=expr.val,
        )


#
# Unknown kind pointers (could be link or property)
#

class PtrTarget(Nonterm):

    def reduce_ARROW_FullTypeExpr(self, *kids):
        _arrow, type_expr = kids

        self.val = type_expr.val
        self.span = type_expr.val.span

    def reduce_COLON_FullTypeExpr(self, *kids):
        _, type_expr = kids
        self.val = type_expr.val
        self.span = type_expr.val.span


class OptPtrTarget(Nonterm):

    def reduce_empty(self, *kids):
        self.val = None

    @parsing.inline(0)
    def reduce_PtrTarget(self, *kids):
        pass


class ConcreteUnknownPointerBlock(Nonterm):
    def _validate(self):
        on_target_delete = None
        for cmd in self.val.commands:
            if isinstance(cmd, qlast.OnTargetDelete):
                if on_target_delete:
                    raise errors.EdgeQLSyntaxError(
                        f"more than one 'on target delete' specification",
                        span=cmd.span)
                else:
                    on_target_delete = cmd

    def _extract_target(self, target, cmds, span, *, overloaded=False):
        if target:
            return target, cmds

        for cmd in cmds:
            if isinstance(cmd, qlast.SetField) and cmd.name == 'expr':
                if target is not None:
                    raise errors.EdgeQLSyntaxError(
                        f'computed link with more than one expression',
                        span=span)
                target = cmd.value

        if not overloaded and target is None:
            raise errors.EdgeQLSyntaxError(
                f'computed link without expression',
                span=span)

        return target, cmds

    def reduce_CreateRegularPointer(self, *kids):
        """%reduce
            PathNodeName OptExtendingSimple
            OptPtrTarget CreateConcreteLinkSDLCommandsBlock
        """
        name, opt_bases, opt_target, block = kids
        target, cmds = self._extract_target(
            opt_target.val, block.val, name.span)
        vbases, vcmds = commondl.extract_bases(opt_bases.val, cmds)
        self.val = qlast.CreateConcreteUnknownPointer(
            name=name.val,
            bases=vbases,
            target=target,
            commands=vcmds,
        )
        self._validate()

    def reduce_CreateRegularQualifiedPointer(self, *kids):
        """%reduce
            PtrQuals PathNodeName OptExtendingSimple
            OptPtrTarget CreateConcreteLinkSDLCommandsBlock
        """
        quals, name, opt_bases, opt_target, block = kids
        target, cmds = self._extract_target(
            opt_target.val, block.val, name.span)
        vbases, vcmds = commondl.extract_bases(opt_bases.val, cmds)
        self.val = qlast.CreateConcreteUnknownPointer(
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
            name=name.val,
            bases=vbases,
            target=target,
            commands=vcmds,
        )
        self._validate()

    def reduce_CreateOverloadedPointer(self, *kids):
        """%reduce
            OVERLOADED PathNodeName OptExtendingSimple
            OptPtrTarget CreateConcreteLinkSDLCommandsBlock
        """
        _, name, opt_bases, opt_target, block = kids
        target, cmds = self._extract_target(
            opt_target.val, block.val, name.span, overloaded=True)
        vbases, vcmds = commondl.extract_bases(opt_bases.val, cmds)
        self.val = qlast.CreateConcreteUnknownPointer(
            name=name.val,
            bases=vbases,
            declared_overloaded=True,
            is_required=None,
            cardinality=None,
            target=target,
            commands=vcmds,
        )
        self._validate()

    def reduce_CreateOverloadedQualifiedPointer(self, *kids):
        """%reduce
            OVERLOADED PtrQuals PathNodeName OptExtendingSimple
            OptPtrTarget CreateConcreteLinkSDLCommandsBlock
        """
        _, quals, name, opt_bases, opt_target, block = kids
        target, cmds = self._extract_target(
            opt_target.val, block.val, name.span, overloaded=True)
        vbases, vcmds = commondl.extract_bases(opt_bases.val, cmds)
        self.val = qlast.CreateConcreteUnknownPointer(
            name=name.val,
            bases=vbases,
            declared_overloaded=True,
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
            target=target,
            commands=vcmds,
        )
        self._validate()


class ConcreteUnknownPointerShort(Nonterm):

    def reduce_CreateRegularPointer(self, *kids):
        """%reduce
            PathNodeName OptExtendingSimple
            PtrTarget
        """
        name, opt_bases, target = kids
        self.val = qlast.CreateConcreteUnknownPointer(
            name=name.val,
            bases=opt_bases.val,
            target=target.val,
        )

    def reduce_CreateRegularQualifiedPointer(self, *kids):
        """%reduce
            PtrQuals PathNodeName OptExtendingSimple
            PtrTarget
        """
        quals, name, opt_bases, target = kids
        self.val = qlast.CreateConcreteUnknownPointer(
            name=name.val,
            bases=opt_bases.val,
            target=target.val,
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
        )

    def reduce_CreateOverloadedPointer(self, *kids):
        """%reduce
            OVERLOADED PathNodeName OptExtendingSimple
            OptPtrTarget
        """
        _, name, opt_bases, opt_target = kids
        self.val = qlast.CreateConcreteUnknownPointer(
            name=name.val,
            bases=opt_bases.val,
            declared_overloaded=True,
            is_required=None,
            cardinality=None,
            target=opt_target.val,
        )

    def reduce_CreateOverloadedQualifiedPointer(self, *kids):
        """%reduce
            OVERLOADED PtrQuals PathNodeName OptExtendingSimple
            OptPtrTarget
        """
        _, quals, name, opt_bases, opt_target = kids
        self.val = qlast.CreateConcreteUnknownPointer(
            name=name.val,
            bases=opt_bases.val,
            declared_overloaded=True,
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
            target=opt_target.val,
        )


# Unknown simple computed pointers can only go on objects, since they
# conflict with SetField on links.
class ConcreteUnknownPointerObjectShort(Nonterm):
    def reduce_CreateComputableUnknownPointer(self, *kids):
        """%reduce
            PathNodeName ASSIGN GenExpr
        """
        name, _, expr = kids
        self.val = qlast.CreateConcreteUnknownPointer(
            name=name.val,
            target=expr.val,
        )

    def reduce_CreateQualifiedComputableUnknownPointer(self, *kids):
        """%reduce
            PtrQuals PathNodeName ASSIGN GenExpr
        """
        quals, name, _, expr = kids
        self.val = qlast.CreateConcreteUnknownPointer(
            name=name.val,
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
            target=expr.val,
        )


#
# Properties
#
sdl_commands_block(
    'CreateProperty',
    Using,
    SetField,
    SetAnnotation,
    commondl.CreateSimpleExtending,
)


class PropertyDeclaration(Nonterm):
    def reduce_CreateProperty(self, *kids):
        r"""%reduce ABSTRACT PROPERTY PtrNodeName OptExtendingSimple \
                    CreatePropertySDLCommandsBlock \
        """
        _, _, name, extending, commands_block = kids

        vbases, vcommands = commondl.extract_bases(
            extending.val,
            commands_block.val
        )
        self.val = qlast.CreateProperty(
            name=name.val,
            bases=vbases,
            commands=vcommands,
            abstract=True,
        )


class PropertyDeclarationShort(Nonterm):
    def reduce_CreateProperty(self, *kids):
        r"""%reduce ABSTRACT PROPERTY PtrNodeName OptExtendingSimple"""
        _, _, name, extending = kids
        self.val = qlast.CreateProperty(
            name=name.val,
            bases=extending.val,
            abstract=True,
        )


sdl_commands_block(
    'CreateConcreteProperty',
    Using,
    SetField,
    SetAnnotation,
    ConcreteConstraintBlock,
    ConcreteConstraintShort,
    RewriteDeclarationBlock,
    RewriteDeclarationShort,
    commondl.CreateSimpleExtending,
)


class ConcretePropertyBlock(Nonterm):
    def _extract_target(self, target, cmds, span, *, overloaded=False):
        if target:
            return target, cmds

        for cmd in cmds:
            if isinstance(cmd, qlast.SetField) and cmd.name == 'expr':
                if target is not None:
                    raise errors.EdgeQLSyntaxError(
                        f'computed property with more than one expression',
                        span=span)
                target = cmd.value

        if not overloaded and target is None:
            raise errors.EdgeQLSyntaxError(
                f'computed property without expression',
                span=span)

        return target, cmds

    def reduce_CreateRegularProperty(self, *kids):
        """%reduce
            PROPERTY PathNodeName OptExtendingSimple
            OptPtrTarget CreateConcretePropertySDLCommandsBlock
        """
        _, name, extending, target, commands_block = kids

        target, cmds = self._extract_target(
            target.val, commands_block.val, name.span
        )
        vbases, vcmds = commondl.extract_bases(extending.val, cmds)
        self.val = qlast.CreateConcreteProperty(
            name=name.val,
            bases=vbases,
            target=target,
            commands=vcmds,
        )

    def reduce_CreateRegularQualifiedProperty(self, *kids):
        """%reduce
            PtrQuals PROPERTY PathNodeName OptExtendingSimple
            OptPtrTarget CreateConcretePropertySDLCommandsBlock
        """
        (quals, property, name, extending, target, commands) = kids

        target, cmds = self._extract_target(
            target.val, commands.val, property.span
        )
        vbases, vcmds = commondl.extract_bases(extending.val, cmds)
        self.val = qlast.CreateConcreteProperty(
            name=name.val,
            bases=vbases,
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
            target=target,
            commands=vcmds,
        )

    def reduce_CreateOverloadedProperty(self, *kids):
        """%reduce
            OVERLOADED PROPERTY PathNodeName OptExtendingSimple
            OptPtrTarget CreateConcretePropertySDLCommandsBlock
        """
        _, _, name, opt_bases, opt_target, block = kids
        target, cmds = self._extract_target(
            opt_target.val, block.val, name.span, overloaded=True)
        vbases, vcmds = commondl.extract_bases(opt_bases.val, cmds)
        self.val = qlast.CreateConcreteProperty(
            name=name.val,
            bases=vbases,
            declared_overloaded=True,
            is_required=None,
            cardinality=None,
            target=target,
            commands=vcmds,
        )

    def reduce_CreateOverloadedQualifiedProperty(self, *kids):
        """%reduce
            OVERLOADED PtrQuals PROPERTY PathNodeName OptExtendingSimple
            OptPtrTarget CreateConcretePropertySDLCommandsBlock
        """
        _, quals, _, name, opt_bases, opt_target, block = kids
        target, cmds = self._extract_target(
            opt_target.val, block.val, name.span, overloaded=True)
        vbases, vcmds = commondl.extract_bases(opt_bases.val, cmds)
        self.val = qlast.CreateConcreteProperty(
            name=name.val,
            bases=vbases,
            declared_overloaded=True,
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
            target=target,
            commands=vcmds,
        )


class ConcretePropertyShort(Nonterm):
    def reduce_CreateRegularProperty(self, *kids):
        """%reduce
            PROPERTY PathNodeName OptExtendingSimple PtrTarget
        """
        _, name, extending, target = kids
        self.val = qlast.CreateConcreteProperty(
            name=name.val,
            bases=extending.val,
            target=target.val,
        )

    def reduce_CreateRegularQualifiedProperty(self, *kids):
        """%reduce
            PtrQuals PROPERTY PathNodeName OptExtendingSimple PtrTarget
        """
        quals, _, name, extending, target = kids
        self.val = qlast.CreateConcreteProperty(
            name=name.val,
            bases=extending.val,
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
            target=target.val,
        )

    def reduce_CreateOverloadedProperty(self, *kids):
        """%reduce
            OVERLOADED PROPERTY PathNodeName OptExtendingSimple
            OptPtrTarget
        """
        _, _, name, opt_bases, opt_target = kids
        self.val = qlast.CreateConcreteProperty(
            name=name.val,
            bases=opt_bases.val,
            declared_overloaded=True,
            is_required=None,
            cardinality=None,
            target=opt_target.val,
        )

    def reduce_CreateOverloadedQualifiedProperty(self, *kids):
        """%reduce
            OVERLOADED PtrQuals PROPERTY PathNodeName OptExtendingSimple
            OptPtrTarget
        """
        _, quals, _, name, opt_bases, opt_target = kids
        self.val = qlast.CreateConcreteProperty(
            name=name.val,
            bases=opt_bases.val,
            declared_overloaded=True,
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
            target=opt_target.val,
        )

    def reduce_CreateComputableProperty(self, *kids):
        """%reduce
            PROPERTY PathNodeName ASSIGN GenExpr
        """
        _, name, _, expr = kids
        self.val = qlast.CreateConcreteProperty(
            name=name.val,
            target=expr.val,
        )

    def reduce_CreateQualifiedComputableProperty(self, *kids):
        """%reduce
            PtrQuals PROPERTY PathNodeName ASSIGN GenExpr
        """
        quals, _, name, _, expr = kids
        self.val = qlast.CreateConcreteProperty(
            name=name.val,
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
            target=expr.val,
        )


#
# Links
#

sdl_commands_block(
    'CreateLink',
    SetField,
    SetAnnotation,
    ConcreteConstraintBlock,
    ConcreteConstraintShort,
    ConcretePropertyBlock,
    ConcretePropertyShort,
    ConcreteUnknownPointerBlock,
    ConcreteUnknownPointerShort,
    ConcreteIndexDeclarationBlock,
    ConcreteIndexDeclarationShort,
    RewriteDeclarationShort,
    RewriteDeclarationBlock,
    commondl.CreateSimpleExtending,
)


class LinkDeclaration(Nonterm):
    def reduce_CreateLink(self, *kids):
        r"""%reduce \
            ABSTRACT LINK PtrNodeName OptExtendingSimple \
            CreateLinkSDLCommandsBlock \
        """
        _, _, name, extending, commands = kids
        vbases, vcommands = commondl.extract_bases(extending.val, commands.val)
        self.val = qlast.CreateLink(
            name=name.val,
            bases=vbases,
            commands=vcommands,
            abstract=True,
        )


class LinkDeclarationShort(Nonterm):
    def reduce_CreateLink(self, *kids):
        r"""%reduce \
            ABSTRACT LINK PtrNodeName OptExtendingSimple"""
        _, _, name, extending = kids
        self.val = qlast.CreateLink(
            name=name.val,
            bases=extending.val,
            abstract=True,
        )


sdl_commands_block(
    'CreateConcreteLink',
    Using,
    SetField,
    SetAnnotation,
    ConcreteConstraintBlock,
    ConcreteConstraintShort,
    ConcretePropertyBlock,
    ConcretePropertyShort,
    ConcreteUnknownPointerBlock,
    ConcreteUnknownPointerShort,
    ConcreteIndexDeclarationBlock,
    ConcreteIndexDeclarationShort,
    commondl.OnTargetDeleteStmt,
    commondl.OnSourceDeleteStmt,
    RewriteDeclarationShort,
    RewriteDeclarationBlock,
    commondl.CreateSimpleExtending,
)


class ConcreteLinkBlock(Nonterm):
    def _validate(self):
        on_target_delete = None
        for cmd in self.val.commands:
            if isinstance(cmd, qlast.OnTargetDelete):
                if on_target_delete:
                    raise errors.EdgeQLSyntaxError(
                        f"more than one 'on target delete' specification",
                        span=cmd.span)
                else:
                    on_target_delete = cmd

    def _extract_target(self, target, cmds, span, *, overloaded=False):
        if target:
            return target, cmds

        for cmd in cmds:
            if isinstance(cmd, qlast.SetField) and cmd.name == 'expr':
                if target is not None:
                    raise errors.EdgeQLSyntaxError(
                        f'computed link with more than one expression',
                        span=span)
                target = cmd.value

        if not overloaded and target is None:
            raise errors.EdgeQLSyntaxError(
                f'computed link without expression',
                span=span)

        return target, cmds

    def reduce_CreateRegularLink(self, *kids):
        """%reduce
            LINK PathNodeName OptExtendingSimple
            OptPtrTarget CreateConcreteLinkSDLCommandsBlock
        """
        _, name, extending, target, commands = kids
        target, cmds = self._extract_target(
            target.val, commands.val, name.span
        )
        vbases, vcmds = commondl.extract_bases(extending.val, cmds)
        self.val = qlast.CreateConcreteLink(
            name=name.val,
            bases=vbases,
            target=target,
            commands=vcmds,
        )
        self._validate()

    def reduce_CreateRegularQualifiedLink(self, *kids):
        """%reduce
            PtrQuals LINK PathNodeName OptExtendingSimple
            OptPtrTarget CreateConcreteLinkSDLCommandsBlock
        """
        quals, _, name, extending, target, commands = kids
        target, cmds = self._extract_target(
            target.val, commands.val, name.span
        )
        vbases, vcmds = commondl.extract_bases(extending.val, cmds)
        self.val = qlast.CreateConcreteLink(
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
            name=name.val,
            bases=vbases,
            target=target,
            commands=vcmds,
        )
        self._validate()

    def reduce_CreateOverloadedLink(self, *kids):
        """%reduce
            OVERLOADED LINK PathNodeName OptExtendingSimple
            OptPtrTarget CreateConcreteLinkSDLCommandsBlock
        """
        _, _, name, opt_bases, opt_target, block = kids
        target, cmds = self._extract_target(
            opt_target.val, block.val, name.span, overloaded=True)
        vbases, vcmds = commondl.extract_bases(opt_bases.val, cmds)
        self.val = qlast.CreateConcreteLink(
            name=name.val,
            bases=vbases,
            declared_overloaded=True,
            is_required=None,
            cardinality=None,
            target=target,
            commands=vcmds,
        )
        self._validate()

    def reduce_CreateOverloadedQualifiedLink(self, *kids):
        """%reduce
            OVERLOADED PtrQuals LINK PathNodeName OptExtendingSimple
            OptPtrTarget CreateConcreteLinkSDLCommandsBlock
        """
        _, quals, _, name, opt_bases, opt_target, block = kids
        target, cmds = self._extract_target(
            opt_target.val, block.val, name.span, overloaded=True)
        vbases, vcmds = commondl.extract_bases(opt_bases.val, cmds)
        self.val = qlast.CreateConcreteLink(
            name=name.val,
            bases=vbases,
            declared_overloaded=True,
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
            target=target,
            commands=vcmds,
        )
        self._validate()


class ConcreteLinkShort(Nonterm):

    def reduce_CreateRegularLink(self, *kids):
        """%reduce
            LINK PathNodeName OptExtendingSimple
            PtrTarget
        """
        _, name, opt_bases, target = kids
        self.val = qlast.CreateConcreteLink(
            name=name.val,
            bases=opt_bases.val,
            target=target.val,
        )

    def reduce_CreateRegularQualifiedLink(self, *kids):
        """%reduce
            PtrQuals LINK PathNodeName OptExtendingSimple
            PtrTarget
        """
        quals, _, name, opt_bases, target = kids
        self.val = qlast.CreateConcreteLink(
            name=name.val,
            bases=opt_bases.val,
            target=target.val,
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
        )

    def reduce_CreateOverloadedLink(self, *kids):
        """%reduce
            OVERLOADED LINK PathNodeName OptExtendingSimple
            OptPtrTarget
        """
        _, _, name, opt_bases, opt_target = kids
        self.val = qlast.CreateConcreteLink(
            name=name.val,
            bases=opt_bases.val,
            declared_overloaded=True,
            is_required=None,
            cardinality=None,
            target=opt_target.val,
        )

    def reduce_CreateOverloadedQualifiedLink(self, *kids):
        """%reduce
            OVERLOADED PtrQuals LINK PathNodeName OptExtendingSimple
            OptPtrTarget
        """
        _, quals, _, name, opt_bases, opt_target = kids
        self.val = qlast.CreateConcreteLink(
            name=name.val,
            bases=opt_bases.val,
            declared_overloaded=True,
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
            target=opt_target.val,
        )

    def reduce_CreateComputableLink(self, *kids):
        """%reduce
            LINK PathNodeName ASSIGN GenExpr
        """
        _, name, _, expr = kids
        self.val = qlast.CreateConcreteLink(
            name=name.val,
            target=expr.val,
        )

    def reduce_CreateQualifiedComputableLink(self, *kids):
        """%reduce
            PtrQuals LINK PathNodeName ASSIGN GenExpr
        """
        quals, _, name, _, expr = kids
        self.val = qlast.CreateConcreteLink(
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
            name=name.val,
            target=expr.val,
        )


#
# Access Policies
#
sdl_commands_block(
    'CreateAccessPolicy',
    SetField,
    SetAnnotation
)


class AccessPolicyDeclarationBlock(Nonterm):
    def reduce_CreateAccessPolicy(self, *kids):
        """%reduce
            ACCESS POLICY ShortNodeName
            OptWhenBlock AccessPolicyAction AccessKindList
            OptUsingBlock
            CreateAccessPolicySDLCommandsBlock
        """
        _, _, name, when, action, access_kinds, using, commands = kids
        self.val = qlast.CreateAccessPolicy(
            name=name.val,
            condition=when.val,
            action=action.val,
            access_kinds=[y for x in access_kinds.val for y in x],
            expr=using.val,
            commands=commands.val,
        )


class AccessPolicyDeclarationShort(Nonterm):
    def reduce_CreateAccessPolicy(self, *kids):
        """%reduce
            ACCESS POLICY ShortNodeName
            OptWhenBlock AccessPolicyAction AccessKindList
            OptUsingBlock
        """
        _, _, name, when, action, access_kinds, using = kids
        self.val = qlast.CreateAccessPolicy(
            name=name.val,
            condition=when.val,
            action=action.val,
            access_kinds=[y for x in access_kinds.val for y in x],
            expr=using.val,
        )


#
# Triggers
#
sdl_commands_block(
    'CreateTrigger',
    SetField,
    SetAnnotation
)


class TriggerDeclarationBlock(Nonterm):
    def reduce_CreateTrigger(self, *kids):
        """%reduce
            TRIGGER NodeName
            TriggerTiming TriggerKindList
            FOR TriggerScope
            OptWhenBlock
            DO ParenExpr
            CreateTriggerSDLCommandsBlock
        """
        _, name, timing, kinds, _, scope, when, _, expr, commands = kids
        self.val = qlast.CreateTrigger(
            name=name.val,
            timing=timing.val,
            kinds=kinds.val,
            scope=scope.val,
            expr=expr.val,
            condition=when.val,
            commands=commands.val,
        )


class TriggerDeclarationShort(Nonterm):
    def reduce_CreateTrigger(self, *kids):
        """%reduce
            TRIGGER NodeName
            TriggerTiming TriggerKindList
            FOR TriggerScope
            OptWhenBlock
            DO ParenExpr
        """
        _, name, timing, kinds, _, scope, when, _, expr = kids
        self.val = qlast.CreateTrigger(
            name=name.val,
            timing=timing.val,
            kinds=kinds.val,
            scope=scope.val,
            expr=expr.val,
            condition=when.val,
        )


#
# Object Types
#

sdl_commands_block(
    'CreateObjectType',
    SetAnnotation,
    ConcretePropertyBlock,
    ConcretePropertyShort,
    ConcreteLinkBlock,
    ConcreteLinkShort,
    ConcreteUnknownPointerBlock,
    ConcreteUnknownPointerShort,
    ConcreteUnknownPointerObjectShort,
    ConcreteConstraintBlock,
    ConcreteConstraintShort,
    ConcreteIndexDeclarationBlock,
    ConcreteIndexDeclarationShort,
    AccessPolicyDeclarationBlock,
    AccessPolicyDeclarationShort,
    TriggerDeclarationBlock,
    TriggerDeclarationShort,
)


class ObjectTypeDeclaration(Nonterm):
    def reduce_CreateAbstractObjectTypeStmt(self, *kids):
        r"""%reduce \
            ABSTRACT TYPE NodeName OptExtendingSimple \
            CreateObjectTypeSDLCommandsBlock \
        """
        _, _, name, extending, commands = kids
        self.val = qlast.CreateObjectType(
            abstract=True,
            name=name.val,
            bases=extending.val,
            commands=commands.val,
        )

    def reduce_CreateRegularObjectTypeStmt(self, *kids):
        r"""%reduce \
            TYPE NodeName OptExtendingSimple \
            CreateObjectTypeSDLCommandsBlock \
        """
        _, name, extending, commands = kids
        self.val = qlast.CreateObjectType(
            name=name.val,
            bases=extending.val,
            commands=commands.val,
        )


class ObjectTypeDeclarationShort(Nonterm):
    def reduce_CreateAbstractObjectTypeStmt(self, *kids):
        r"""%reduce \
            ABSTRACT TYPE NodeName OptExtendingSimple"""
        _, _, name, extending = kids
        self.val = qlast.CreateObjectType(
            abstract=True,
            name=name.val,
            bases=extending.val,
        )

    def reduce_CreateRegularObjectTypeStmt(self, *kids):
        r"""%reduce \
            TYPE NodeName OptExtendingSimple"""
        _, name, extending = kids
        self.val = qlast.CreateObjectType(
            name=name.val,
            bases=extending.val,
        )


#
# Aliases
#

sdl_commands_block(
    'CreateAlias',
    Using,
    SetField,
    SetAnnotation,
    opt=False
)


class AliasDeclaration(Nonterm):
    def reduce_CreateAliasRegularStmt(self, *kids):
        r"""%reduce
            ALIAS NodeName CreateAliasSDLCommandsBlock
        """
        _, name, commands = kids
        self.val = qlast.CreateAlias(
            name=name.val,
            commands=commands.val,
        )


class AliasDeclarationShort(Nonterm):
    def reduce_CreateAliasShortStmt(self, *kids):
        r"""%reduce
            ALIAS NodeName ASSIGN GenExpr
        """
        _, name, _, expr = kids
        self.val = qlast.CreateAlias(
            name=name.val,
            commands=[
                qlast.SetField(
                    name='expr',
                    value=expr.val,
                    special_syntax=True,
                    span=self.span,
                )
            ]
        )

    def reduce_CreateAliasRegularStmt(self, *kids):
        r"""%reduce
            ALIAS NodeName CreateAliasSingleSDLCommandBlock
        """
        _, name, commands = kids
        self.val = qlast.CreateAlias(
            name=name.val,
            commands=commands.val,
        )


#
# Functions
#


sdl_commands_block(
    'CreateFunction',
    commondl.FromFunction,
    SetField,
    SetAnnotation,
    opt=False
)


class FunctionDeclaration(Nonterm, commondl.ProcessFunctionBlockMixin):
    def reduce_CreateFunction(self, *kids):
        r"""%reduce FUNCTION NodeName CreateFunctionArgs \
                FunctionResult CreateFunctionSDLCommandsBlock
        """
        _, name, args, result, body = kids
        self.val = qlast.CreateFunction(
            name=name.val,
            params=args.val,
            returning=result.val.result_type,
            returning_typemod=result.val.type_qualifier,
            **self._process_function_body(body),
        )


class FunctionDeclarationShort(Nonterm, commondl.ProcessFunctionBlockMixin):
    def reduce_CreateFunction(self, *kids):
        r"""%reduce FUNCTION NodeName CreateFunctionArgs \
                FunctionResult CreateFunctionSingleSDLCommandBlock
        """
        _, name, args, result, body = kids
        self.val = qlast.CreateFunction(
            name=name.val,
            params=args.val,
            returning=result.val.result_type,
            returning_typemod=result.val.type_qualifier,
            **self._process_function_body(body),
        )


#
# Globals
#

sdl_commands_block(
    'CreateGlobal',
    Using,
    SetField,
    SetAnnotation,
)


class GlobalDeclaration(Nonterm):
    def _extract_target(self, target, cmds, span, *, overloaded=False):
        if target:
            return target, cmds

        for cmd in cmds:
            if isinstance(cmd, qlast.SetField) and cmd.name == 'expr':
                if target is not None:
                    raise errors.EdgeQLSyntaxError(
                        f'computed global with more than one expression',
                        span=span)
                target = cmd.value

        if not overloaded and target is None:
            raise errors.EdgeQLSyntaxError(
                f'computed property without expression',
                span=span)

        return target, cmds

    def reduce_CreateGlobalQuals(self, *kids):
        """%reduce
            PtrQuals GLOBAL NodeName
            OptPtrTarget CreateGlobalSDLCommandsBlock
        """
        quals, glob, name, target, commands = kids
        target, cmds = self._extract_target(
            target.val, commands.val, glob.span
        )
        self.val = qlast.CreateGlobal(
            name=name.val,
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
            target=target,
            commands=cmds,
        )

    def reduce_CreateGlobal(self, *kids):
        """%reduce
            GLOBAL NodeName
            OptPtrTarget CreateGlobalSDLCommandsBlock
        """
        glob, name, target, commands = kids
        target, cmds = self._extract_target(
            target.val, commands.val, glob.span
        )
        self.val = qlast.CreateGlobal(
            name=name.val,
            target=target,
            commands=cmds,
        )


class GlobalDeclarationShort(Nonterm):
    def reduce_CreateRegularGlobalShortQuals(self, *kids):
        """%reduce
            PtrQuals GLOBAL NodeName PtrTarget
        """
        quals, _, name, target = kids
        self.val = qlast.CreateGlobal(
            name=name.val,
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
            target=target.val,
        )

    def reduce_CreateRegularGlobalShort(self, *kids):
        """%reduce
            GLOBAL NodeName PtrTarget
        """
        _, name, target = kids
        self.val = qlast.CreateGlobal(
            name=name.val,
            target=target.val,
        )

    def reduce_CreateComputedGlobalShortQuals(self, *kids):
        """%reduce
            PtrQuals GLOBAL NodeName ASSIGN GenExpr
        """
        quals, _, name, _, expr = kids
        self.val = qlast.CreateGlobal(
            name=name.val,
            is_required=quals.val.required,
            cardinality=quals.val.cardinality,
            target=expr.val,
        )

    def reduce_CreateComputedGlobalShort(self, *kids):
        """%reduce
            GLOBAL NodeName ASSIGN GenExpr
        """
        _, name, _, expr = kids
        self.val = qlast.CreateGlobal(
            name=name.val,
            target=expr.val,
        )


#
# Permissions
#


sdl_commands_block(
    'CreatePermission',
    SetAnnotation,
)


class PermissionDeclaration(Nonterm):
    def reduce_CreatePermission(self, *kids):
        """%reduce
            PERMISSION NodeName
            CreatePermissionSDLCommandsBlock
        """
        _, name, commands = kids
        self.val = qlast.CreatePermission(
            name=name.val,
            commands=commands.val,
        )


class PermissionDeclarationShort(Nonterm):
    def reduce_CreatePermission(self, *kids):
        """%reduce
            PERMISSION NodeName
        """
        _, name = kids
        self.val = qlast.CreatePermission(
            name=name.val,
        )
