
from data_ops import *


from functools import singledispatch



from .data_ops import *
from helper_funcs import *
import sys
import traceback
from edb.edgeql import ast as qlast
from edb import edgeql
from edb import errors

import pprint

from shape_ops import *

from edb.common import debug, parsing
from typing import *

def elab_error(msg : str, ctx : parsing.ParserContext):
    raise errors.QueryError(msg, context=ctx)


@singledispatch
def elab(node: qlast.Base) -> Expr:
    debug.dump(node)
    raise ValueError("Not Implemented!")

@elab.register(qlast.InsertQuery)
def elab_InsertQuery(expr : qlast.InsertQuery) -> InsertExpr:
    debug.dump(expr)
    subject_type = expr.subject.name
    object_shape = elab(expr.shape)
    object_expr = shape_to_expr(object_shape)
    return InsertExpr(name=subject_type, new=object_expr)


@elab.register(qlast.StringConstant)
def elab_string_constant(e : qlast.StringConstant) -> StrVal: 
    return StrVal(val=e.value)

@elab.register(qlast.Shape)
def elab_Shape(elements : List[qlast.ShapeElement]) -> Shape:
    """ Convert a concrete syntax shape to object expressions"""
    result = {}
    [result := {**result, name : e } if name not in result.keys() else (elab_error("Duplicate Value in Shapes", se.ctx))
    for se in elements
    for (name, e) in [elab(se)]]
    return result

@elab.register(qlast.ShapeElement)
def elab_ShapeElement(e : qlast.ShapeElement) -> Tuple[str, BindingExpr]:
    match e.expr:
        case qlast.Path(steps=[qlast.Ptr(ptr=qlast.ObjectRef(name=pname), direction=s_pointers.PointerDirection.Outbound)]):
            comp = e.compexpr
            return [pname, to_expr(comp)]
            # if isinstance(comp, qlast.Shape):
            #     return [pname, shapeToObjectExpr(comp)]
            # else:
            #     raise ValueError("No Imp", comp)
        case qlast.Path(steps=st):
            raise ValueError(st)

    raise errors.QueryError(
             "mutation queries must specify values with ':='",
             context=e.context,
         )
    
# @to_expr.register(qlast.Shape)
# def to_expr_shape(shape : qlast.Shape) -> Expr:
    
