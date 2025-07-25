#
# This source file is part of the EdgeDB open source project.
#
# Copyright 2008-present MagicStack Inc. and the EdgeDB authors.
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

from typing import (
    Any,
    Callable,
    cast,
    Iterable,
    Iterator,
    Mapping,
    NoReturn,
    Optional,
    overload,
    Self,
    TYPE_CHECKING,
)

import abc
import collections
import itertools

import immutables as immu

from edb import errors
from edb.common import adapter
from edb.common import english
from edb.common import lru

from . import casts as s_casts
from . import functions as s_func
from . import migrations as s_migrations
from . import modules as s_mod
from . import name as sn
from . import objects as so
from . import operators as s_oper
from . import pseudo as s_pseudo
from . import types as s_types

if TYPE_CHECKING:
    import uuid
    from edb.common import parsing

    Refs_T = immu.Map[
        uuid.UUID,
        immu.Map[
            tuple[type[so.Object], str],
            immu.Map[uuid.UUID, None],
        ],
    ]

EXT_MODULE = sn.UnqualName('ext')

STD_MODULES = (
    sn.UnqualName('std'),
    sn.UnqualName('schema'),
    sn.UnqualName('std::math'),
    sn.UnqualName('sys'),
    sn.UnqualName('sys::perm'),
    sn.UnqualName('cfg'),
    sn.UnqualName('cfg::perm'),
    sn.UnqualName('std::cal'),
    sn.UnqualName('std::net'),
    sn.UnqualName('std::net::http'),
    sn.UnqualName('std::net::perm'),
    sn.UnqualName('std::pg'),
    sn.UnqualName('std::_test'),
    sn.UnqualName('std::fts'),
    sn.UnqualName('std::lang'),
    sn.UnqualName('std::lang::go'),
    sn.UnqualName('std::lang::js'),
    sn.UnqualName('std::lang::py'),
    sn.UnqualName('std::lang::rs'),
    EXT_MODULE,
    sn.UnqualName('std::enc'),
)

SPECIAL_MODULES = (
    sn.UnqualName('__derived__'),
    sn.UnqualName('__ext_casts__'),
    sn.UnqualName('__ext_index_matches__'),
)

# Specifies the order of processing of files and directories in lib/
STD_SOURCES = (
    sn.UnqualName('std'),
    sn.UnqualName('schema'),
    sn.UnqualName('math'),
    sn.UnqualName('sys'),
    sn.UnqualName('cfg'),
    sn.UnqualName('cal'),
    sn.UnqualName('ext'),
    sn.UnqualName('enc'),
    sn.UnqualName('pg'),
    sn.UnqualName('fts'),
    sn.UnqualName('net'),
)
TESTMODE_SOURCES = (
    sn.UnqualName('_testmode'),
)


class Schema(abc.ABC):

    @abc.abstractmethod
    def add_raw(
        self: Self,
        id: uuid.UUID,
        sclass: type[so.Object],
        data: tuple[Any, ...],
    ) -> Self:
        raise NotImplementedError

    @abc.abstractmethod
    def add(
        self: Self,
        id: uuid.UUID,
        sclass: type[so.Object],
        data: tuple[Any, ...],
    ) -> Self:
        raise NotImplementedError

    @abc.abstractmethod
    def discard(self: Self, obj: so.Object) -> Self:
        raise NotImplementedError

    @abc.abstractmethod
    def delete(self: Self, obj: so.Object) -> Self:
        raise NotImplementedError

    @abc.abstractmethod
    def delist(self: Self, name: sn.Name) -> Self:
        raise NotImplementedError

    @abc.abstractmethod
    def update_obj(
        self: Self,
        obj: so.Object,
        updates: Mapping[str, Any],
    ) -> Self:
        raise NotImplementedError

    @abc.abstractmethod
    def maybe_get_obj_data_raw(
        self,
        obj: so.Object,
    ) -> Optional[tuple[Any, ...]]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_obj_data_raw(
        self,
        obj: so.Object,
    ) -> tuple[Any, ...]:
        raise NotImplementedError

    @abc.abstractmethod
    def set_obj_field(
        self: Self,
        obj: so.Object,
        field: str,
        value: Any,
    ) -> Self:
        raise NotImplementedError

    @abc.abstractmethod
    def unset_obj_field(
        self: Self,
        obj: so.Object,
        field: str,
    ) -> Self:
        raise NotImplementedError

    @abc.abstractmethod
    def get_functions(
        self,
        name: str | sn.Name,
        default: tuple[s_func.Function, ...] | so.NoDefaultT = so.NoDefault,
        *,
        module_aliases: Optional[Mapping[Optional[str], str]] = None,
        disallow_module: Optional[Callable[[str], bool]] = None,
    ) -> tuple[s_func.Function, ...]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_operators(
        self,
        name: str | sn.Name,
        default: tuple[s_oper.Operator, ...] | so.NoDefaultT = so.NoDefault,
        *,
        module_aliases: Optional[Mapping[Optional[str], str]] = None,
        disallow_module: Optional[Callable[[str], bool]] = None,
    ) -> tuple[s_oper.Operator, ...]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_casts_to_type(
        self,
        to_type: s_types.Type,
        *,
        implicit: bool = False,
        assignment: bool = False,
    ) -> frozenset[s_casts.Cast]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_casts_from_type(
        self,
        from_type: s_types.Type,
        *,
        implicit: bool = False,
        assignment: bool = False,
    ) -> frozenset[s_casts.Cast]:
        raise NotImplementedError

    @overload
    def get_referrers(
        self,
        scls: so.Object,
        *,
        scls_type: type[so.Object_T],
        field_name: Optional[str] = None,
    ) -> frozenset[so.Object_T]:
        ...

    @overload
    def get_referrers(
        self,
        scls: so.Object,
        *,
        scls_type: None = None,
        field_name: Optional[str] = None,
    ) -> frozenset[so.Object]:
        ...

    @abc.abstractmethod
    def get_referrers(
        self,
        scls: so.Object,
        *,
        scls_type: Optional[type[so.Object_T]] = None,
        field_name: Optional[str] = None,
    ) -> frozenset[so.Object_T]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_referrers_ex(
        self,
        scls: so.Object,
        *,
        scls_type: Optional[type[so.Object_T]] = None,
    ) -> dict[
        tuple[type[so.Object_T], str],
        frozenset[so.Object_T],
    ]:
        raise NotImplementedError

    @overload
    def get_by_id(
        self,
        obj_id: uuid.UUID,
        default: so.Object | so.NoDefaultT = so.NoDefault,
        *,
        type: None = None,
    ) -> so.Object:
        ...

    @overload
    def get_by_id(
        self,
        obj_id: uuid.UUID,
        default: so.Object_T | so.NoDefaultT = so.NoDefault,
        *,
        type: Optional[type[so.Object_T]] = None,
    ) -> so.Object_T:
        ...

    @overload
    def get_by_id(
        self,
        obj_id: uuid.UUID,
        default: None = None,
        *,
        type: Optional[type[so.Object_T]] = None,
    ) -> Optional[so.Object_T]:
        ...

    def get_by_id(
        self,
        obj_id: uuid.UUID,
        default: so.Object_T | so.NoDefaultT | None = so.NoDefault,
        *,
        type: Optional[type[so.Object_T]] = None,
    ) -> Optional[so.Object_T]:
        return self._get_by_id(obj_id, default, type=type)

    @abc.abstractmethod
    def _get_by_id(
        self,
        obj_id: uuid.UUID,
        default: so.Object_T | so.NoDefaultT | None = so.NoDefault,
        *,
        type: Optional[type[so.Object_T]] = None,
    ) -> Optional[so.Object_T]:
        raise NotImplementedError

    @overload
    def get_global(
        self,
        objtype: type[so.Object_T],
        name: str | sn.Name,
        default: so.Object_T | so.NoDefaultT = so.NoDefault,
    ) -> so.Object_T:
        ...

    @overload
    def get_global(
        self,
        objtype: type[so.Object_T],
        name: str | sn.Name,
        default: None = None,
    ) -> Optional[so.Object_T]:
        ...

    def get_global(
        self,
        objtype: type[so.Object_T],
        name: str | sn.Name,
        default: so.Object_T | so.NoDefaultT | None = so.NoDefault,
    ) -> Optional[so.Object_T]:
        return self._get_global(objtype, name, default)

    @abc.abstractmethod
    def _get_global(
        self,
        objtype: type[so.Object_T],
        name: str | sn.Name,
        default: so.Object_T | so.NoDefaultT | None,
    ) -> Optional[so.Object_T]:
        raise NotImplementedError

    @overload
    def get(
        self,
        name: str | sn.Name,
        default: so.Object_T | so.NoDefaultT = so.NoDefault,
        *,
        module_aliases: Optional[Mapping[Optional[str], str]] = None,
        condition: Optional[Callable[[so.Object], bool]] = None,
        label: Optional[str] = None,
        span: Optional[parsing.Span] = None,
    ) -> so.Object:
        ...

    @overload
    def get(
        self,
        name: str | sn.Name,
        default: None,
        *,
        module_aliases: Optional[Mapping[Optional[str], str]] = None,
        condition: Optional[Callable[[so.Object], bool]] = None,
        label: Optional[str] = None,
        span: Optional[parsing.Span] = None,
    ) -> Optional[so.Object]:
        ...

    @overload
    def get(
        self,
        name: str | sn.Name,
        default: so.Object_T | so.NoDefaultT = so.NoDefault,
        *,
        module_aliases: Optional[Mapping[Optional[str], str]] = None,
        type: type[so.Object_T],
        condition: Optional[Callable[[so.Object], bool]] = None,
        label: Optional[str] = None,
        span: Optional[parsing.Span] = None,
    ) -> so.Object_T:
        ...

    @overload
    def get(
        self,
        name: str | sn.Name,
        default: None,
        *,
        module_aliases: Optional[Mapping[Optional[str], str]] = None,
        type: type[so.Object_T],
        condition: Optional[Callable[[so.Object], bool]] = None,
        label: Optional[str] = None,
        span: Optional[parsing.Span] = None,
    ) -> Optional[so.Object_T]:
        ...

    @overload
    def get(
        self,
        name: str | sn.Name,
        default: so.Object | so.NoDefaultT | None = so.NoDefault,
        *,
        module_aliases: Optional[Mapping[Optional[str], str]] = None,
        type: Optional[type[so.Object_T]] = None,
        condition: Optional[Callable[[so.Object], bool]] = None,
        label: Optional[str] = None,
        span: Optional[parsing.Span] = None,
    ) -> Optional[so.Object]:
        ...

    def get(
        self,
        name: str | sn.Name,
        default: so.Object | so.NoDefaultT | None = so.NoDefault,
        *,
        module_aliases: Optional[Mapping[Optional[str], str]] = None,
        type: Optional[type[so.Object_T]] = None,
        condition: Optional[Callable[[so.Object], bool]] = None,
        label: Optional[str] = None,
        span: Optional[parsing.Span] = None,
    ) -> Optional[so.Object]:
        return self._get(
            name,
            default,
            module_aliases=module_aliases,
            type=type,
            condition=condition,
            label=label,
            span=span,
        )

    @abc.abstractmethod
    def _get(
        self,
        name: str | sn.Name,
        default: so.Object | so.NoDefaultT | None,
        *,
        module_aliases: Optional[Mapping[Optional[str], str]],
        type: Optional[type[so.Object_T]],
        condition: Optional[Callable[[so.Object], bool]],
        label: Optional[str],
        span: Optional[parsing.Span],
        disallow_module: Optional[Callable[[str], bool]] = None,
    ) -> Optional[so.Object]:
        raise NotImplementedError

    def _get_object_ids(self) -> Iterable[uuid.UUID]:
        raise NotImplementedError

    @abc.abstractmethod
    def has_object(self, object_id: uuid.UUID) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def has_module(self, module: str) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def has_migration(self, name: str) -> bool:
        raise NotImplementedError

    def get_children(
        self,
        scls: so.Object_T,
    ) -> frozenset[so.Object_T]:
        # Ideally get_referrers needs to be made generic via
        # an overload on scls_type, but mypy crashes on that.
        return self.get_referrers(
            scls,
            scls_type=type(scls),
            field_name='bases',
        )

    def get_descendants(
        self,
        scls: so.Object_T,
    ) -> frozenset[so.Object_T]:
        return self.get_referrers(
            scls, scls_type=type(scls), field_name='ancestors')

    @abc.abstractmethod
    def get_objects(
        self,
        *,
        exclude_stdlib: bool = False,
        exclude_global: bool = False,
        exclude_extensions: bool = False,
        exclude_internal: bool = True,
        included_modules: Optional[Iterable[sn.Name]] = None,
        excluded_modules: Optional[Iterable[sn.Name]] = None,
        included_items: Optional[Iterable[sn.Name]] = None,
        excluded_items: Optional[Iterable[sn.Name]] = None,
        type: Optional[type[so.Object_T]] = None,
        extra_filters: Iterable[Callable[[Schema, so.Object_T], bool]] = (),
    ) -> SchemaIterator[so.Object_T]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_modules(self) -> tuple[s_mod.Module, ...]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_last_migration(self) -> Optional[s_migrations.Migration]:
        raise NotImplementedError

    @staticmethod
    def raise_wrong_type(
        name: str | sn.Name,
        actual_type: type[so.Object_T],
        expected_type: type[so.Object_T],
        span: Optional[parsing.Span],
    ) -> NoReturn:
        refname = str(name)

        actual_type_name = actual_type.get_schema_class_displayname()
        expected_type_name = expected_type.get_schema_class_displayname()
        raise errors.InvalidReferenceError(
            f'{refname!r} exists, but is {english.add_a(actual_type_name)}, '
            f'not {english.add_a(expected_type_name)}',
            span=span,
        )

    @staticmethod
    def raise_bad_reference(
        name: str | sn.Name,
        *,
        label: Optional[str] = None,
        module_aliases: Optional[Mapping[Optional[str], str]] = None,
        span: Optional[parsing.Span] = None,
        type: Optional[type[so.Object]] = None,
    ) -> NoReturn:
        refname = str(name)

        if label is None:
            if type is not None:
                label = type.get_schema_class_displayname()
            else:
                label = 'schema item'

        if type is not None:
            if issubclass(type, so.QualifiedObject):
                if not sn.is_qualified(refname):
                    if module_aliases is not None:
                        default_module = module_aliases.get(None)
                        if default_module is not None:
                            refname = type.get_displayname_static(
                                sn.QualName(default_module, refname),
                            )
                else:
                    refname = type.get_displayname_static(
                        sn.QualName.from_string(refname))
            else:
                refname = type.get_displayname_static(
                    sn.UnqualName.from_string(refname))

        raise errors.InvalidReferenceError(
            f'{label} {refname!r} does not exist',
            span=span,
        )


class FlatSchema(Schema):

    _id_to_data: immu.Map[uuid.UUID, tuple[Any, ...]]
    _id_to_type: immu.Map[uuid.UUID, str]
    _name_to_id: immu.Map[sn.Name, uuid.UUID]
    _shortname_to_id: immu.Map[
        tuple[type[so.Object], sn.Name],
        frozenset[uuid.UUID],
    ]
    _globalname_to_id: immu.Map[
        tuple[type[so.Object], sn.Name],
        uuid.UUID,
    ]
    _refs_to: Refs_T
    _generation: int

    def __init__(self) -> None:
        self._id_to_data = immu.Map()
        self._id_to_type = immu.Map()
        self._shortname_to_id = immu.Map()
        self._name_to_id = immu.Map()
        self._globalname_to_id = immu.Map()
        self._refs_to = immu.Map()
        self._generation = 0

    def _get_object_ids(self) -> Iterable[uuid.UUID]:
        return self._id_to_type.keys()

    def _replace(
        self,
        *,
        id_to_data: Optional[immu.Map[uuid.UUID, tuple[Any, ...]]] = None,
        id_to_type: Optional[immu.Map[uuid.UUID, str]] = None,
        name_to_id: Optional[immu.Map[sn.Name, uuid.UUID]] = None,
        shortname_to_id: Optional[
            immu.Map[
                tuple[type[so.Object], sn.Name],
                frozenset[uuid.UUID]
            ]
        ] = None,
        globalname_to_id: Optional[
            immu.Map[tuple[type[so.Object], sn.Name], uuid.UUID]
        ] = None,
        refs_to: Optional[Refs_T] = None,
    ) -> FlatSchema:
        new = FlatSchema.__new__(FlatSchema)

        if id_to_data is None:
            new._id_to_data = self._id_to_data
        else:
            new._id_to_data = id_to_data

        if id_to_type is None:
            new._id_to_type = self._id_to_type
        else:
            new._id_to_type = id_to_type

        if name_to_id is None:
            new._name_to_id = self._name_to_id
        else:
            new._name_to_id = name_to_id

        if shortname_to_id is None:
            new._shortname_to_id = self._shortname_to_id
        else:
            new._shortname_to_id = shortname_to_id

        if globalname_to_id is None:
            new._globalname_to_id = self._globalname_to_id
        else:
            new._globalname_to_id = globalname_to_id

        if refs_to is None:
            new._refs_to = self._refs_to
        else:
            new._refs_to = refs_to

        new._generation = self._generation + 1

        return new

    def _update_obj_name(
        self,
        obj_id: uuid.UUID,
        sclass: type[so.Object],
        old_name: Optional[sn.Name],
        new_name: Optional[sn.Name],
    ) -> tuple[
        immu.Map[sn.Name, uuid.UUID],
        immu.Map[tuple[type[so.Object], sn.Name], frozenset[uuid.UUID]],
        immu.Map[tuple[type[so.Object], sn.Name], uuid.UUID],
    ]:
        name_to_id = self._name_to_id
        shortname_to_id = self._shortname_to_id
        globalname_to_id = self._globalname_to_id
        is_global = not issubclass(sclass, so.QualifiedObject)

        has_sn_cache = issubclass(sclass, (s_func.Function, s_oper.Operator))

        if old_name is not None:
            if is_global:
                globalname_to_id = globalname_to_id.delete((sclass, old_name))
            else:
                name_to_id = name_to_id.delete(old_name)
            if has_sn_cache:
                old_shortname = sn.shortname_from_fullname(old_name)
                sn_key = (sclass, old_shortname)

                new_ids = shortname_to_id[sn_key] - {obj_id}
                if new_ids:
                    shortname_to_id = shortname_to_id.set(sn_key, new_ids)
                else:
                    shortname_to_id = shortname_to_id.delete(sn_key)

        if new_name is not None:
            if is_global:
                key = (sclass, new_name)
                if key in globalname_to_id:
                    other_obj = self.get_by_id(
                        globalname_to_id[key], type=so.Object)
                    vn = other_obj.get_verbosename(self, with_parent=True)
                    raise errors.SchemaError(
                        f'{vn} already exists')
                globalname_to_id = globalname_to_id.set(key, obj_id)
            else:
                assert isinstance(new_name, sn.QualName)
                if (
                    not self.has_module(new_name.module)
                    and new_name.get_module_name() not in SPECIAL_MODULES
                ):
                    raise errors.UnknownModuleError(
                        f'module {new_name.module!r} is not in this schema')

                if new_name in name_to_id:
                    other_obj = self.get_by_id(
                        name_to_id[new_name], type=so.Object)
                    vn = other_obj.get_verbosename(self, with_parent=True)
                    raise errors.SchemaError(
                        f'{vn} already exists')
                name_to_id = name_to_id.set(new_name, obj_id)

            if has_sn_cache:
                new_shortname = sn.shortname_from_fullname(new_name)
                sn_key = (sclass, new_shortname)

                try:
                    ids = shortname_to_id[sn_key]
                except KeyError:
                    ids = frozenset()

                shortname_to_id = shortname_to_id.set(sn_key, ids | {obj_id})

        return name_to_id, shortname_to_id, globalname_to_id

    def update_obj(
        self,
        obj: so.Object,
        updates: Mapping[str, Any],
    ) -> FlatSchema:
        if not updates:
            return self

        obj_id = obj.id
        sclass = type(obj)
        all_fields = sclass.get_schema_fields()
        object_ref_fields = sclass.get_object_reference_fields()
        reducible_fields = sclass.get_reducible_fields()

        try:
            data = list(self._id_to_data[obj_id])
        except KeyError:
            data = [None] * len(all_fields)

        name_to_id = None
        shortname_to_id = None
        globalname_to_id = None
        orig_refs = {}
        new_refs = {}

        for fieldname, value in updates.items():
            field = all_fields[fieldname]
            findex = field.index
            if fieldname == 'name':
                name_to_id, shortname_to_id, globalname_to_id = (
                    self._update_obj_name(
                        obj_id,
                        sclass,
                        data[findex],
                        value
                    )
                )

            if value is None:
                if field in reducible_fields and field in object_ref_fields:
                    orig_value = data[findex]
                    if orig_value is not None:
                        orig_refs[fieldname] = (
                            field.type.schema_refs_from_data(orig_value))
            else:
                if field in reducible_fields:
                    value = value.schema_reduce()
                    if field in object_ref_fields:
                        new_refs[fieldname] = (
                            field.type.schema_refs_from_data(value))
                        orig_value = data[findex]
                        if orig_value is not None:
                            orig_refs[fieldname] = (
                                field.type.schema_refs_from_data(orig_value))

            data[findex] = value

        id_to_data = self._id_to_data.set(obj_id, tuple(data))
        refs_to = self._update_refs_to(obj_id, sclass, orig_refs, new_refs)

        return self._replace(name_to_id=name_to_id,
                             shortname_to_id=shortname_to_id,
                             globalname_to_id=globalname_to_id,
                             id_to_data=id_to_data,
                             refs_to=refs_to)

    def maybe_get_obj_data_raw(
        self,
        obj: so.Object,
    ) -> Optional[tuple[Any, ...]]:
        return self._id_to_data.get(obj.id)

    def get_obj_data_raw(
        self,
        obj: so.Object,
    ) -> tuple[Any, ...]:
        try:
            return self._id_to_data[obj.id]
        except KeyError:
            err = (f'cannot get item data: item {str(obj.id)!r} '
                   f'is not present in the schema {self!r}')
            raise errors.SchemaError(err) from None

    def set_obj_field(
        self,
        obj: so.Object,
        fieldname: str,
        value: Any,
    ) -> FlatSchema:
        obj_id = obj.id

        try:
            data = self._id_to_data[obj_id]
        except KeyError:
            err = (f'cannot set {fieldname!r} value: item {str(obj_id)!r} '
                   f'is not present in the schema {self!r}')
            raise errors.SchemaError(err) from None

        sclass = so.ObjectMeta.get_schema_class(self._id_to_type[obj_id])

        field = sclass.get_schema_field(fieldname)
        findex = field.index
        is_object_ref = field in sclass.get_object_reference_fields()

        if field in sclass.get_reducible_fields():
            value = value.schema_reduce()

        name_to_id = None
        shortname_to_id = None
        globalname_to_id = None
        if fieldname == 'name':
            old_name = data[findex]
            name_to_id, shortname_to_id, globalname_to_id = (
                self._update_obj_name(obj_id, sclass, old_name, value)
            )

        data_list = list(data)
        data_list[findex] = value
        new_data = tuple(data_list)

        id_to_data = self._id_to_data.set(obj_id, new_data)

        if not is_object_ref:
            refs_to = None
        else:
            orig_value = data[findex]
            if orig_value is not None:
                orig_refs = {
                    fieldname: field.type.schema_refs_from_data(orig_value),
                }
            else:
                orig_refs = {}

            new_refs = {fieldname: field.type.schema_refs_from_data(value)}
            refs_to = self._update_refs_to(obj_id, sclass, orig_refs, new_refs)

        return self._replace(
            name_to_id=name_to_id,
            shortname_to_id=shortname_to_id,
            globalname_to_id=globalname_to_id,
            id_to_data=id_to_data,
            refs_to=refs_to,
        )

    def unset_obj_field(
        self,
        obj: so.Object,
        fieldname: str,
    ) -> FlatSchema:
        obj_id = obj.id

        try:
            data = self._id_to_data[obj.id]
        except KeyError:
            return self

        sclass = so.ObjectMeta.get_schema_class(self._id_to_type[obj.id])
        field = sclass.get_schema_field(fieldname)
        findex = field.index

        name_to_id = None
        shortname_to_id = None
        globalname_to_id = None
        orig_value = data[findex]

        if orig_value is None:
            return self

        if fieldname == 'name':
            name_to_id, shortname_to_id, globalname_to_id = (
                self._update_obj_name(
                    obj_id,
                    sclass,
                    orig_value,
                    None
                )
            )

        data_list = list(data)
        data_list[findex] = None
        new_data = tuple(data_list)

        id_to_data = self._id_to_data.set(obj_id, new_data)
        is_object_ref = field in sclass.get_object_reference_fields()

        if not is_object_ref:
            refs_to = None
        else:
            orig_refs = {
                fieldname: field.type.schema_refs_from_data(orig_value),
            }
            refs_to = self._update_refs_to(obj_id, sclass, orig_refs, None)

        return self._replace(
            name_to_id=name_to_id,
            shortname_to_id=shortname_to_id,
            globalname_to_id=globalname_to_id,
            id_to_data=id_to_data,
            refs_to=refs_to,
        )

    def _update_refs_to(
        self,
        object_id: uuid.UUID,
        sclass: type[so.Object],
        orig_refs: Optional[Mapping[str, frozenset[uuid.UUID]]],
        new_refs: Optional[Mapping[str, frozenset[uuid.UUID]]],
    ) -> Refs_T:
        objfields = sclass.get_object_reference_fields()
        if not objfields:
            return self._refs_to

        with self._refs_to.mutate() as mm:
            for field in objfields:
                if not new_refs:
                    ids = None
                else:
                    ids = new_refs.get(field.name)

                if not orig_refs:
                    orig_ids = None
                else:
                    orig_ids = orig_refs.get(field.name)

                if not ids and not orig_ids:
                    continue

                old_ids: Optional[frozenset[uuid.UUID]]
                new_ids: Optional[frozenset[uuid.UUID]]

                key = (sclass, field.name)

                if ids and orig_ids:
                    new_ids = ids - orig_ids
                    old_ids = orig_ids - ids
                elif ids:
                    new_ids = ids
                    old_ids = None
                else:
                    new_ids = None
                    old_ids = orig_ids

                if new_ids:
                    for ref_id in new_ids:
                        try:
                            refs = mm[ref_id]
                        except KeyError:
                            mm[ref_id] = immu.Map((
                                (key, immu.Map(((object_id, None),))),
                            ))
                        else:
                            try:
                                field_refs = refs[key]
                            except KeyError:
                                field_refs = immu.Map(((object_id, None),))
                            else:
                                field_refs = field_refs.set(object_id, None)
                            mm[ref_id] = refs.set(key, field_refs)

                if old_ids:
                    for ref_id in old_ids:
                        refs = mm[ref_id]
                        field_refs = refs[key].delete(object_id)
                        if not field_refs:
                            mm[ref_id] = refs.delete(key)
                        else:
                            mm[ref_id] = refs.set(key, field_refs)

            result = mm.finish()

        return result

    def add_raw(
        self,
        id: uuid.UUID,
        sclass: type[so.Object],
        data: tuple[Any, ...],
    ) -> FlatSchema:
        name_field = sclass.get_schema_field('name')
        name = data[name_field.index]

        if name in self._name_to_id:
            other_obj = self.get_by_id(
                self._name_to_id[name], type=so.Object)
            vn = other_obj.get_verbosename(self, with_parent=True)
            raise errors.SchemaError(f'{vn} already exists')

        if id in self._id_to_data:
            raise errors.SchemaError(
                f'{sclass.__name__} ({str(id)!r}) is already present '
                f'in the schema {self!r}')

        object_ref_fields = sclass.get_object_reference_fields()
        if not object_ref_fields:
            refs_to = None
        else:
            new_refs = {}
            for field in object_ref_fields:
                ref_data = data[field.index]
                if ref_data is not None:
                    ref = field.type.schema_refs_from_data(ref_data)
                    new_refs[field.name] = ref
            refs_to = self._update_refs_to(id, sclass, None, new_refs)

        name_to_id, shortname_to_id, globalname_to_id = self._update_obj_name(
            id, sclass, None, name)

        updates = dict(
            id_to_data=self._id_to_data.set(id, data),
            id_to_type=self._id_to_type.set(id, sclass.__name__),
            name_to_id=name_to_id,
            shortname_to_id=shortname_to_id,
            globalname_to_id=globalname_to_id,
            refs_to=refs_to,
        )

        if (
            issubclass(sclass, so.QualifiedObject)
            and not self.has_module(name.module)
            and name.get_module_name() not in SPECIAL_MODULES
        ):
            raise errors.UnknownModuleError(
                f'module {name.module!r} is not in this schema')

        return self._replace(**updates)  # type: ignore

    def add(
        self,
        id: uuid.UUID,
        sclass: type[so.Object],
        data: tuple[Any, ...],
    ) -> FlatSchema:
        reducible_fields = sclass.get_reducible_fields()
        if reducible_fields:
            data_list = list(data)
            for field in reducible_fields:
                val = data[field.index]
                if val is not None:
                    data_list[field.index] = val.schema_reduce()
            data = tuple(data_list)

        return self.add_raw(id, sclass, data)

    def delist(self, name: sn.Name) -> FlatSchema:
        name_to_id = self._name_to_id.delete(name)
        return self._replace(
            name_to_id=name_to_id,
            shortname_to_id=self._shortname_to_id,
            globalname_to_id=self._globalname_to_id,
        )

    def _delete(self, obj: so.Object) -> FlatSchema:
        data = self._id_to_data.get(obj.id)
        if data is None:
            raise errors.InvalidReferenceError(
                f'cannot delete {obj!r}: not in this schema')

        sclass = type(obj)
        name_field = sclass.get_schema_field('name')
        name = data[name_field.index]

        updates = {}

        name_to_id, shortname_to_id, globalname_to_id = self._update_obj_name(
            obj.id, sclass, name, None)

        object_ref_fields = sclass.get_object_reference_fields()
        if not object_ref_fields:
            refs_to = None
        else:
            values = self._id_to_data[obj.id]
            orig_refs = {}
            for field in object_ref_fields:
                ref = values[field.index]
                if ref is not None:
                    ref = field.type.schema_refs_from_data(ref)
                    orig_refs[field.name] = ref

            refs_to = self._update_refs_to(obj.id, sclass, orig_refs, None)

        updates.update(dict(
            name_to_id=name_to_id,
            shortname_to_id=shortname_to_id,
            globalname_to_id=globalname_to_id,
            id_to_data=self._id_to_data.delete(obj.id),
            id_to_type=self._id_to_type.delete(obj.id),
            refs_to=refs_to,
        ))

        return self._replace(**updates)  # type: ignore

    def discard(self, obj: so.Object) -> FlatSchema:
        if obj.id in self._id_to_data:
            return self._delete(obj)
        else:
            return self

    def delete(self, obj: so.Object) -> FlatSchema:
        return self._delete(obj)

    def _search_with_getter(
        self,
        name: str | sn.Name,
        *,
        getter: Callable[[FlatSchema, sn.Name], Any],
        default: Any,
        module_aliases: Optional[Mapping[Optional[str], str]],
        disallow_module: Optional[Callable[[str], bool]],
    ) -> Any:
        """
        Find something in the schema with a given name.

        This function mostly mirrors edgeql.tracer.resolve_name
        except:
        - When searching in std, disallow some modules (often the base modules)
        - If no result found, return default
        """
        if isinstance(name, str):
            name = sn.name_from_string(name)
        shortname = name.name
        module = name.module if isinstance(name, sn.QualName) else None
        orig_module = module

        if module == '__std__':
            fqname = sn.QualName('std', shortname)
            result = getter(self, fqname)
            if result is not None:
                return result
            else:
                return default

        # Apply module aliases
        current_module = (
            module_aliases[None]
            if module_aliases and None in module_aliases else
            None
        )
        is_current, module = apply_module_aliases(
            module, module_aliases, current_module,
        )
        if is_current and current_module is None:
            return default

        no_std = is_current

        # Check if something matches the name
        if module is not None:
            fqname = sn.QualName(module, shortname)
            result = getter(self, fqname)
            if result is not None:
                return result

        # Try something in std if __current__ was not specified
        if not no_std:
            # If module == None, look in std
            if orig_module is None:
                mod_name = 'std'
                fqname = sn.QualName(mod_name, shortname)
                result = getter(self, fqname)
                if result is not None:
                    return result

            # Ensure module is not a base module.
            # Then try the module as part of std.
            if module and not (
                self.has_module(fmod := module.split('::')[0])
                or (disallow_module and disallow_module(fmod))
            ):
                mod_name = f'std::{module}'
                fqname = sn.QualName(mod_name, shortname)
                result = getter(self, fqname)
                if result is not None:
                    return result

        return default

    def get_functions(
        self,
        name: str | sn.Name,
        default: tuple[s_func.Function, ...] | so.NoDefaultT = so.NoDefault,
        *,
        module_aliases: Optional[Mapping[Optional[str], str]] = None,
        disallow_module: Optional[Callable[[str], bool]] = None,
    ) -> tuple[s_func.Function, ...]:
        if isinstance(name, str):
            name = sn.name_from_string(name)
        funcs = self._search_with_getter(
            name,
            getter=_get_functions,
            module_aliases=module_aliases,
            default=default,
            disallow_module=disallow_module,
        )

        if funcs is not so.NoDefault:
            return cast(
                tuple[s_func.Function, ...],
                funcs,
            )
        else:
            return Schema.raise_bad_reference(
                name=name,
                module_aliases=module_aliases,
                type=s_func.Function,
            )

    def get_operators(
        self,
        name: str | sn.Name,
        default: tuple[s_oper.Operator, ...] | so.NoDefaultT = so.NoDefault,
        *,
        module_aliases: Optional[Mapping[Optional[str], str]] = None,
        disallow_module: Optional[Callable[[str], bool]] = None,
    ) -> tuple[s_oper.Operator, ...]:
        funcs = self._search_with_getter(
            name,
            getter=_get_operators,
            module_aliases=module_aliases,
            default=default,
            disallow_module=disallow_module,
        )

        if funcs is not so.NoDefault:
            return cast(
                tuple[s_oper.Operator, ...],
                funcs,
            )
        else:
            return Schema.raise_bad_reference(
                name=name,
                module_aliases=module_aliases,
                type=s_oper.Operator,
            )

    @lru.lru_method_cache()
    def _get_casts(
        self,
        stype: s_types.Type,
        *,
        disposition: str,
        implicit: bool = False,
        assignment: bool = False,
    ) -> frozenset[s_casts.Cast]:

        all_casts = cast(
            frozenset[s_casts.Cast],
            self.get_referrers(
                stype, scls_type=s_casts.Cast, field_name=disposition),
        )

        casts = []
        for castobj in all_casts:
            if implicit and not castobj.get_allow_implicit(self):
                continue
            if assignment and not castobj.get_allow_assignment(self):
                continue
            casts.append(castobj)

        return frozenset(casts)

    def get_casts_to_type(
        self,
        to_type: s_types.Type,
        *,
        implicit: bool = False,
        assignment: bool = False,
    ) -> frozenset[s_casts.Cast]:
        return self._get_casts(to_type, disposition='to_type',
                               implicit=implicit, assignment=assignment)

    def get_casts_from_type(
        self,
        from_type: s_types.Type,
        *,
        implicit: bool = False,
        assignment: bool = False,
    ) -> frozenset[s_casts.Cast]:
        return self._get_casts(from_type, disposition='from_type',
                               implicit=implicit, assignment=assignment)

    def get_referrers(
        self,
        scls: so.Object,
        *,
        scls_type: Optional[type[so.Object_T]] = None,
        field_name: Optional[str] = None,
    ) -> frozenset[so.Object_T]:
        return self._get_referrers(
            scls, scls_type=scls_type, field_name=field_name)

    @lru.lru_method_cache()
    def _get_referrers(
        self,
        scls: so.Object,
        *,
        scls_type: Optional[type[so.Object_T]] = None,
        field_name: Optional[str] = None,
    ) -> frozenset[so.Object_T]:

        try:
            refs = self._refs_to[scls.id]
        except KeyError:
            return frozenset()
        else:
            referrers: set[so.Object] = set()

            if scls_type is not None:
                if field_name is not None:
                    for (st, fn), ids in refs.items():
                        if issubclass(st, scls_type) and fn == field_name:
                            referrers.update(
                                self.get_by_id(objid) for objid in ids)
                else:
                    for (st, _), ids in refs.items():
                        if issubclass(st, scls_type):
                            referrers.update(
                                self.get_by_id(objid) for objid in ids)
            elif field_name is not None:
                for (_, fn), ids in refs.items():
                    if fn == field_name:
                        referrers.update(
                            self.get_by_id(objid) for objid in ids)
            else:
                refids = itertools.chain.from_iterable(refs.values())
                referrers.update(self.get_by_id(objid) for objid in refids)

            return frozenset(referrers)  # type: ignore

    @lru.lru_method_cache()
    def get_referrers_ex(
        self,
        scls: so.Object,
        *,
        scls_type: Optional[type[so.Object_T]] = None,
    ) -> dict[
        tuple[type[so.Object_T], str],
        frozenset[so.Object_T],
    ]:
        try:
            refs = self._refs_to[scls.id]
        except KeyError:
            return {}
        else:
            result = {}

            if scls_type is not None:
                for (st, fn), ids in refs.items():
                    if issubclass(st, scls_type):
                        result[st, fn] = frozenset(
                            self.get_by_id(objid) for objid in ids)
            else:
                for (st, fn), ids in refs.items():
                    result[st, fn] = frozenset(  # type: ignore
                        self.get_by_id(objid) for objid in ids)

            return result  # type: ignore

    def _get_by_id(
        self,
        obj_id: uuid.UUID,
        default: so.Object_T | so.NoDefaultT | None = so.NoDefault,
        *,
        type: Optional[type[so.Object_T]] = None,
        # Deep u-optimization; this is the hottest path in the system,
        # so avoid needing to do lookups for this function.
        _raw_schema_restore: Callable[[str, uuid.UUID], so.Object] = (
            so.Object.raw_schema_restore),
    ) -> Optional[so.Object_T]:
        try:
            sclass_name = self._id_to_type[obj_id]
        except KeyError:
            if default is so.NoDefault:
                raise LookupError(
                    f'reference to a non-existent schema item {obj_id}'
                    f' in schema {self!r}'
                ) from None
            else:
                return default
        else:
            obj = _raw_schema_restore(sclass_name, obj_id)
            if type is not None and not isinstance(obj, type):
                raise TypeError(
                    f'schema object {obj_id!r} exists, but is a '
                    f'{obj.__class__.get_schema_class_displayname()!r}, '
                    f'not a {type.get_schema_class_displayname()!r}'
                )

            # Avoid the overhead of cast(Object_T) below
            return obj  # type: ignore

    # Important micro-optimization
    if not TYPE_CHECKING:
        get_by_id = _get_by_id

    def _get_global(
        self,
        objtype: type[so.Object_T],
        name: str | sn.Name,
        default: so.Object_T | so.NoDefaultT | None,
    ) -> Optional[so.Object_T]:
        if isinstance(name, str):
            name = sn.UnqualName(name)
        obj_id = self._globalname_to_id.get((objtype, name))
        if obj_id is not None:
            return self.get_by_id(obj_id)  # type: ignore
        elif default is not so.NoDefault:
            return default
        else:
            Schema.raise_bad_reference(name, type=objtype)

    def _get(
        self,
        name: str | sn.Name,
        default: so.Object | so.NoDefaultT | None,
        *,
        module_aliases: Optional[Mapping[Optional[str], str]],
        type: Optional[type[so.Object_T]],
        condition: Optional[Callable[[so.Object], bool]],
        label: Optional[str],
        span: Optional[parsing.Span],
        disallow_module: Optional[Callable[[str], bool]] = None,
    ) -> Optional[so.Object]:
        def getter(schema: FlatSchema, name: sn.Name) -> Optional[so.Object]:
            obj_id = schema._name_to_id.get(name)
            if obj_id is None:
                return None

            obj = schema.get_by_id(obj_id, default=None)
            if obj is not None and condition is not None:
                if not condition(obj):
                    obj = None
            return obj

        obj = self._search_with_getter(
            name,
            getter=getter,
            module_aliases=module_aliases,
            default=default,
            disallow_module=disallow_module,
        )

        if obj is not so.NoDefault:
            # We do our own type check, instead of using get_by_id's, so
            # we can produce a user-facing error message.
            if obj and type is not None and not isinstance(obj, type):
                Schema.raise_wrong_type(name, obj.__class__, type, span)

            return obj  # type: ignore
        else:
            Schema.raise_bad_reference(
                name=name,
                label=label,
                module_aliases=module_aliases,
                span=span,
                type=type,
            )

    def has_object(self, object_id: uuid.UUID) -> bool:
        return object_id in self._id_to_type

    def has_module(self, module: str) -> bool:
        return self.get_global(s_mod.Module, module, None) is not None

    def has_migration(self, name: str) -> bool:
        return self.get_global(s_migrations.Migration, name, None) is not None

    def get_objects(
        self,
        *,
        exclude_stdlib: bool = False,
        exclude_global: bool = False,
        exclude_extensions: bool = False,
        exclude_internal: bool = True,
        included_modules: Optional[Iterable[sn.Name]] = None,
        excluded_modules: Optional[Iterable[sn.Name]] = None,
        included_items: Optional[Iterable[sn.Name]] = None,
        excluded_items: Optional[Iterable[sn.Name]] = None,
        type: Optional[type[so.Object_T]] = None,
        extra_filters: Iterable[Callable[[Schema, so.Object_T], bool]] = (),
    ) -> SchemaIterator[so.Object_T]:
        return SchemaIterator[so.Object_T](
            self,
            self._id_to_type,
            exclude_stdlib=exclude_stdlib,
            exclude_global=exclude_global,
            exclude_extensions=exclude_extensions,
            exclude_internal=exclude_internal,
            included_modules=included_modules,
            excluded_modules=excluded_modules,
            included_items=included_items,
            excluded_items=excluded_items,
            type=type,
            extra_filters=extra_filters,
        )

    def get_modules(self) -> tuple[s_mod.Module, ...]:
        modules = []
        for (objtype, _), objid in self._globalname_to_id.items():
            if objtype is s_mod.Module:
                modules.append(self.get_by_id(objid, type=s_mod.Module))
        return tuple(modules)

    def get_last_migration(self) -> Optional[s_migrations.Migration]:
        return _get_last_migration(self)

    def __repr__(self) -> str:
        return (
            f'<{type(self).__name__} gen:{self._generation} at {id(self):#x}>')


def apply_module_aliases(
    module: Optional[str],
    module_aliases: Optional[Mapping[Optional[str], str]],
    current_module: Optional[str],
) -> tuple[bool, Optional[str]]:
    is_current = False
    if module and module.startswith('__current__::'):
        # Replace __current__ with default module
        is_current = True
        if current_module is not None:
            module = f'{current_module}::{module.removeprefix("__current__::")}'
        else:
            module = None
    elif module_aliases is not None:
        # Apply modalias
        first: Optional[str]
        if module:
            first, sep, rest = module.partition('::')
        else:
            first, sep, rest = module, '', ''

        fq_module = module_aliases.get(first)
        if fq_module is not None:
            module = fq_module + sep + rest

    return is_current, module


EMPTY_SCHEMA = FlatSchema()


def upgrade_schema(schema: FlatSchema) -> FlatSchema:
    """Repair a schema object serialized by an older patch version

    When an edgeql+schema patch adds fields to schema types, old
    serialized schemas will be broken, since their tuples are missing
    the fields.

    In this situation, we run through all the data tuples and fill
    them out. The upgraded version will then be cached.
    """

    cls_fields = {}
    for py_cls in so.ObjectMeta.get_schema_metaclasses():
        if isinstance(py_cls, adapter.Adapter):
            continue

        fields = py_cls._schema_fields.values()
        cls_fields[py_cls] = sorted(fields, key=lambda f: f.index)

    id_to_data = schema._id_to_data
    fixes = {}
    for id, typ_name in schema._id_to_type.items():
        data = id_to_data[id]
        obj = so.Object.schema_restore((typ_name, id))
        typ = type(obj)

        tfields = cls_fields[typ]
        exp_len = len(tfields)
        if len(data) < exp_len:
            ldata = list(data)
            for _ in range(len(ldata), exp_len):
                ldata.append(None)

            fixes[id] = tuple(ldata)

    return schema._replace(id_to_data=id_to_data.update(fixes))


class SchemaIterator[Object_T: so.Object]:
    def __init__(
        self,
        schema: Schema,
        object_ids: Iterable[uuid.UUID],
        *,
        exclude_stdlib: bool = False,
        exclude_global: bool = False,
        exclude_extensions: bool = False,
        exclude_internal: bool = True,
        included_modules: Optional[Iterable[sn.Name]],
        excluded_modules: Optional[Iterable[sn.Name]],
        included_items: Optional[Iterable[sn.Name]] = None,
        excluded_items: Optional[Iterable[sn.Name]] = None,
        type: Optional[type[Object_T]] = None,
        extra_filters: Iterable[Callable[[Schema, Object_T], bool]] = (),
    ) -> None:

        filters = []

        if type is not None:
            t = type
            filters.append(lambda schema, obj: isinstance(obj, t))

        if included_modules:
            modules = frozenset(included_modules)
            filters.append(
                lambda schema, obj:
                    isinstance(obj, so.QualifiedObject) and
                    obj.get_name(schema).get_module_name() in modules)

        if excluded_modules or exclude_stdlib:
            excmod: set[sn.Name] = set()
            if excluded_modules:
                excmod.update(excluded_modules)
            if exclude_stdlib:
                excmod.update(STD_MODULES)
            filters.append(
                lambda schema, obj: (
                    not isinstance(obj, so.QualifiedObject)
                    or obj.get_name(schema).get_module_name() not in excmod
                )
            )

        if included_items:
            objs = frozenset(included_items)
            filters.append(
                lambda schema, obj: obj.get_name(schema) in objs)

        if excluded_items:
            objs = frozenset(excluded_items)
            filters.append(
                lambda schema, obj: obj.get_name(schema) not in objs)

        if exclude_stdlib:
            filters.append(
                lambda schema, obj: not isinstance(obj, s_pseudo.PseudoType)
            )

        if exclude_extensions:
            filters.append(
                lambda schema, obj:
                obj.get_name(schema).get_root_module_name() != EXT_MODULE
            )

        if exclude_global:
            filters.append(
                lambda schema, obj: not isinstance(obj, so.GlobalObject)
            )

        if exclude_internal:
            filters.append(
                lambda schema, obj: not isinstance(obj, so.InternalObject)
            )

        # Extra filters are last, because they might depend on type.
        filters.extend(extra_filters)

        self._filters = filters
        self._schema = schema
        self._object_ids = object_ids

    def __iter__(self) -> Iterator[Object_T]:
        filters = self._filters
        schema = self._schema
        get_by_id = schema.get_by_id
        for obj_id in self._object_ids:
            obj = get_by_id(obj_id)
            if all(f(self._schema, obj) for f in filters):
                yield obj  # type: ignore


class ChainedSchema(Schema):

    __slots__ = ('_base_schema', '_top_schema', '_global_schema')

    def __init__(
        self, base_schema: Schema, top_schema: Schema, global_schema: Schema
    ) -> None:
        self._base_schema = base_schema
        self._top_schema = top_schema
        self._global_schema = global_schema

    def _get_object_ids(self) -> Iterable[uuid.UUID]:
        return itertools.chain(
            self._base_schema._get_object_ids(),
            self._top_schema._get_object_ids(),
            self._global_schema._get_object_ids(),
        )

    def get_top_schema(self) -> Schema:
        return self._top_schema

    def get_global_schema(self) -> Schema:
        return self._global_schema

    def add_raw(
        self,
        id: uuid.UUID,
        sclass: type[so.Object],
        data: tuple[Any, ...],
    ) -> ChainedSchema:
        if issubclass(sclass, so.GlobalObject):
            return ChainedSchema(
                self._base_schema,
                self._top_schema,
                self._global_schema.add_raw(id, sclass, data),
            )
        else:
            return ChainedSchema(
                self._base_schema,
                self._top_schema.add_raw(id, sclass, data),
                self._global_schema,
            )

    def add(
        self,
        id: uuid.UUID,
        sclass: type[so.Object],
        data: tuple[Any, ...],
    ) -> ChainedSchema:
        if issubclass(sclass, so.GlobalObject):
            return ChainedSchema(
                self._base_schema,
                self._top_schema,
                self._global_schema.add(id, sclass, data),
            )
        else:
            return ChainedSchema(
                self._base_schema,
                self._top_schema.add(id, sclass, data),
                self._global_schema,
            )

    def discard(self, obj: so.Object) -> ChainedSchema:
        if isinstance(obj, so.GlobalObject):
            return ChainedSchema(
                self._base_schema,
                self._top_schema,
                self._global_schema.discard(obj),
            )
        else:
            return ChainedSchema(
                self._base_schema,
                self._top_schema.discard(obj),
                self._global_schema,
            )

    def delete(self, obj: so.Object) -> ChainedSchema:
        if isinstance(obj, so.GlobalObject):
            return ChainedSchema(
                self._base_schema,
                self._top_schema,
                self._global_schema.delete(obj),
            )
        else:
            return ChainedSchema(
                self._base_schema,
                self._top_schema.delete(obj),
                self._global_schema,
            )

    def delist(
        self,
        name: sn.Name,
    ) -> ChainedSchema:
        return ChainedSchema(
            self._base_schema,
            self._top_schema.delist(name),
            self._global_schema,
        )

    def update_obj(
        self,
        obj: so.Object,
        updates: Mapping[str, Any],
    ) -> ChainedSchema:
        if isinstance(obj, so.GlobalObject):
            return ChainedSchema(
                self._base_schema,
                self._top_schema,
                self._global_schema.update_obj(obj, updates),
            )
        else:
            obj_id = obj.id
            base_obj = self._base_schema.get_by_id(obj_id, default=None)
            if (
                base_obj is not None
                and not self._top_schema.has_object(obj_id)
            ):
                top_schema = self._top_schema.add_raw(
                    obj_id,
                    type(base_obj),
                    self._base_schema._id_to_data[obj_id],
                )
            else:
                top_schema = self._top_schema

            return ChainedSchema(
                self._base_schema,
                top_schema.update_obj(obj, updates),
                self._global_schema,
            )

    def maybe_get_obj_data_raw(
        self,
        obj: so.Object,
    ) -> Optional[tuple[Any, ...]]:
        if obj.is_global_object:
            return self._global_schema.maybe_get_obj_data_raw(obj)
        else:
            top = self._top_schema.maybe_get_obj_data_raw(obj)
            if top is not None:
                return top
            else:
                return self._base_schema.maybe_get_obj_data_raw(obj)

    def get_obj_data_raw(
        self,
        obj: so.Object,
    ) -> tuple[Any, ...]:
        top = self._top_schema.maybe_get_obj_data_raw(obj)
        if top is not None:
            return top
        else:
            try:
                return self._base_schema.get_obj_data_raw(obj)
            except errors.SchemaError:
                if obj.is_global_object:
                    return self._global_schema.get_obj_data_raw(obj)
                else:
                    raise

    def set_obj_field(
        self,
        obj: so.Object,
        fieldname: str,
        value: Any,
    ) -> ChainedSchema:
        if isinstance(obj, so.GlobalObject):
            return ChainedSchema(
                self._base_schema,
                self._top_schema,
                self._global_schema.set_obj_field(obj, fieldname, value),
            )
        else:
            return ChainedSchema(
                self._base_schema,
                self._top_schema.set_obj_field(obj, fieldname, value),
                self._global_schema,
            )

    def unset_obj_field(
        self,
        obj: so.Object,
        field: str,
    ) -> ChainedSchema:
        if isinstance(obj, so.GlobalObject):
            return ChainedSchema(
                self._base_schema,
                self._top_schema,
                self._global_schema.unset_obj_field(obj, field),
            )
        else:
            return ChainedSchema(
                self._base_schema,
                self._top_schema.unset_obj_field(obj, field),
                self._global_schema,
            )

    def get_functions(
        self,
        name: str | sn.Name,
        default: tuple[s_func.Function, ...] | so.NoDefaultT = so.NoDefault,
        *,
        module_aliases: Optional[Mapping[Optional[str], str]] = None,
        disallow_module: Optional[Callable[[str], bool]] = None,
    ) -> tuple[s_func.Function, ...]:
        objs = self._top_schema.get_functions(
            name,
            module_aliases=module_aliases,
            default=(),
            disallow_module=disallow_module,
        )
        if not objs:
            if disallow_module is not None:
                dm = disallow_module
                disallow_module = (
                    lambda s: dm(s) or self._top_schema.has_module(s))
            else:
                disallow_module = self._top_schema.has_module
            objs = self._base_schema.get_functions(
                name,
                default=default,
                module_aliases=module_aliases,
                disallow_module=disallow_module,
            )
        return objs

    def get_operators(
        self,
        name: str | sn.Name,
        default: tuple[s_oper.Operator, ...] | so.NoDefaultT = so.NoDefault,
        *,
        module_aliases: Optional[Mapping[Optional[str], str]] = None,
        disallow_module: Optional[Callable[[str], bool]] = None,
    ) -> tuple[s_oper.Operator, ...]:
        objs = self._top_schema.get_operators(
            name,
            module_aliases=module_aliases,
            default=(),
            disallow_module=disallow_module,
        )
        if not objs:
            if disallow_module is not None:
                dm = disallow_module
                disallow_module = (
                    lambda s: dm(s) or self._top_schema.has_module(s))
            else:
                disallow_module = self._top_schema.has_module
            objs = self._base_schema.get_operators(
                name,
                default=default,
                module_aliases=module_aliases,
                disallow_module=disallow_module,
            )
        return objs

    def get_casts_to_type(
        self,
        to_type: s_types.Type,
        *,
        implicit: bool = False,
        assignment: bool = False,
    ) -> frozenset[s_casts.Cast]:
        return (
            self._base_schema.get_casts_to_type(
                to_type,
                implicit=implicit,
                assignment=assignment,
            )
            | self._top_schema.get_casts_to_type(
                to_type,
                implicit=implicit,
                assignment=assignment,
            )
        )

    def get_casts_from_type(
        self,
        from_type: s_types.Type,
        *,
        implicit: bool = False,
        assignment: bool = False,
    ) -> frozenset[s_casts.Cast]:
        return (
            self._base_schema.get_casts_from_type(
                from_type,
                implicit=implicit,
                assignment=assignment,
            )
            | self._top_schema.get_casts_from_type(
                from_type,
                implicit=implicit,
                assignment=assignment,
            )
        )

    def get_referrers(
        self,
        scls: so.Object,
        *,
        scls_type: Optional[type[so.Object_T]] = None,
        field_name: Optional[str] = None,
    ) -> frozenset[so.Object_T]:
        return (
            self._base_schema.get_referrers(  # type: ignore [return-value]
                scls,
                scls_type=scls_type,
                field_name=field_name,
            )
            | self._top_schema.get_referrers(
                scls,
                scls_type=scls_type,
                field_name=field_name,
            )
            | self._global_schema.get_referrers(  # type: ignore [operator]
                scls,
                scls_type=scls_type,
                field_name=field_name,
            )
        )

    def get_referrers_ex(
        self,
        scls: so.Object,
        *,
        scls_type: Optional[type[so.Object_T]] = None,
    ) -> dict[
        tuple[type[so.Object_T], str],
        frozenset[so.Object_T],
    ]:
        base = self._base_schema.get_referrers_ex(scls, scls_type=scls_type)
        top = self._top_schema.get_referrers_ex(scls, scls_type=scls_type)
        gl = self._global_schema.get_referrers_ex(scls, scls_type=scls_type)
        return {
            k: (
                base.get(k, frozenset())
                | top.get(k, frozenset())
                | gl.get(k, frozenset())
            )
            for k in itertools.chain(base, top)
        }

    def _get_by_id(
        self,
        obj_id: uuid.UUID,
        default: so.Object_T | so.NoDefaultT | None = so.NoDefault,
        *,
        type: Optional[type[so.Object_T]] = None,
    ) -> Optional[so.Object_T]:
        obj = self._top_schema.get_by_id(obj_id, type=type, default=None)
        if obj is None:
            obj = self._base_schema.get_by_id(
                obj_id, default=None, type=type)
            if obj is None:
                obj = self._global_schema.get_by_id(
                    obj_id, default=default, type=type)
        return obj

    # Important micro-optimization
    if not TYPE_CHECKING:
        get_by_id = _get_by_id

    def _get_global(
        self,
        objtype: type[so.Object_T],
        name: str | sn.Name,
        default: so.Object_T | so.NoDefaultT | None,
    ) -> Optional[so.Object_T]:
        if issubclass(objtype, so.GlobalObject):
            return self._global_schema.get_global(  # type: ignore
                objtype, name, default=default)
        else:
            obj = self._top_schema.get_global(objtype, name, default=None)
            if obj is None:
                obj = self._base_schema.get_global(
                    objtype, name, default=default)
            return obj

    def _get(
        self,
        name: str | sn.Name,
        default: so.Object | so.NoDefaultT | None,
        *,
        module_aliases: Optional[Mapping[Optional[str], str]],
        type: Optional[type[so.Object_T]],
        condition: Optional[Callable[[so.Object], bool]],
        label: Optional[str],
        span: Optional[parsing.Span],
        disallow_module: Optional[Callable[[str], bool]] = None,
    ) -> Optional[so.Object]:
        obj = self._top_schema._get(
            name,
            module_aliases=module_aliases,
            type=type,
            default=None,
            condition=condition,
            label=label,
            span=span,
            disallow_module=disallow_module,
        )
        if obj is None:
            if disallow_module is not None:
                dm = disallow_module
                disallow_module = (
                    lambda s: dm(s) or self._top_schema.has_module(s))
            else:
                disallow_module = self._top_schema.has_module
            return self._base_schema._get(
                name,
                default=default,
                module_aliases=module_aliases,
                type=type,
                condition=condition,
                label=label,
                span=span,
                disallow_module=disallow_module,
            )
        else:
            return obj

    def has_object(self, object_id: uuid.UUID) -> bool:
        return (
            self._base_schema.has_object(object_id)
            or self._top_schema.has_object(object_id)
            or self._global_schema.has_object(object_id)
        )

    def has_module(self, module: str) -> bool:
        return (
            self._base_schema.has_module(module)
            or self._top_schema.has_module(module)
        )

    def has_migration(self, name: str) -> bool:
        return (
            self._base_schema.has_migration(name)
            or self._top_schema.has_migration(name)
        )

    def get_objects(
        self,
        *,
        exclude_stdlib: bool = False,
        exclude_global: bool = False,
        exclude_extensions: bool = False,
        exclude_internal: bool = True,
        included_modules: Optional[Iterable[sn.Name]] = None,
        excluded_modules: Optional[Iterable[sn.Name]] = None,
        included_items: Optional[Iterable[sn.Name]] = None,
        excluded_items: Optional[Iterable[sn.Name]] = None,
        type: Optional[type[so.Object_T]] = None,
        extra_filters: Iterable[Callable[[Schema, so.Object_T], bool]] = (),
    ) -> SchemaIterator[so.Object_T]:
        return SchemaIterator[so.Object_T](
            self,
            self._get_object_ids(),
            exclude_global=exclude_global,
            exclude_stdlib=exclude_stdlib,
            exclude_extensions=exclude_extensions,
            exclude_internal=exclude_internal,
            included_modules=included_modules,
            excluded_modules=excluded_modules,
            included_items=included_items,
            excluded_items=excluded_items,
            type=type,
            extra_filters=extra_filters,
        )

    def get_modules(self) -> tuple[s_mod.Module, ...]:
        return (
            self._base_schema.get_modules()
            + self._top_schema.get_modules()
        )

    def get_last_migration(self) -> Optional[s_migrations.Migration]:
        migration = self._top_schema.get_last_migration()
        if migration is None:
            migration = self._base_schema.get_last_migration()
        return migration


@lru.per_job_lru_cache()
def _get_functions(
    schema: FlatSchema,
    name: sn.Name,
) -> Optional[tuple[s_func.Function, ...]]:
    objids = schema._shortname_to_id.get((s_func.Function, name))
    if objids is None:
        return None
    return cast(
        tuple[s_func.Function, ...],
        tuple(schema.get_by_id(oid) for oid in objids),
    )


@lru.per_job_lru_cache()
def _get_operators(
    schema: FlatSchema,
    name: sn.Name,
) -> Optional[tuple[s_oper.Operator, ...]]:
    objids = schema._shortname_to_id.get((s_oper.Operator, name))
    if objids is None:
        return None
    else:
        return tuple(
            schema.get_by_id(oid, type=s_oper.Operator) for oid in objids
        )


@lru.per_job_lru_cache()
def _get_last_migration(
    schema: FlatSchema,
) -> Optional[s_migrations.Migration]:

    migrations = cast(
        list[s_migrations.Migration],
        [
            schema.get_by_id(mid)
            for (t, _), mid in schema._globalname_to_id.items()
            if t is s_migrations.Migration
        ],
    )

    if not migrations:
        return None

    migration_map = collections.defaultdict(list)
    root = None
    for m in migrations:
        parents = m.get_parents(schema).objects(schema)
        if not parents:
            if root is not None:
                raise errors.InternalServerError(
                    'multiple migration roots found')
            root = m
        for parent in parents:
            migration_map[parent].append(m)

    if root is None:
        raise errors.InternalServerError('cannot find migration root')

    latest = root
    while children := migration_map[latest]:
        if len(children) > 1:
            raise errors.InternalServerError(
                'nonlinear migration history detected')
        latest = children[0]

    return latest
