use std::{marker::PhantomData, str::Utf8Error};

use super::{
    arrays::{array_access, Array, ArrayMeta},
    field_access,
    writer::BufWriter,
    Enliven, FieldAccess, Meta,
};

pub mod meta {
    pub use super::EncodedMeta as Encoded;
    pub use super::LengthMeta as Length;
    pub use super::RestMeta as Rest;
    pub use super::ZTStringMeta as ZTString;
}

/// Represents the remainder of data in a message.
#[derive(Debug, PartialEq, Eq)]
pub struct Rest<'a> {
    buf: &'a [u8],
}

field_access!(RestMeta);

pub struct RestMeta {}
impl Meta for RestMeta {
    fn name(&self) -> &'static str {
        "Rest"
    }
}
impl Enliven for RestMeta {
    type WithLifetime<'a> = Rest<'a>;
    type ForMeasure<'a> = &'a [u8];
    type ForBuilder<'a> = &'a [u8];
}

impl<'a> Rest<'a> {}

impl<'a> AsRef<[u8]> for Rest<'a> {
    fn as_ref(&self) -> &[u8] {
        self.buf
    }
}

impl<'a> std::ops::Deref for Rest<'a> {
    type Target = [u8];
    fn deref(&self) -> &Self::Target {
        self.buf
    }
}

impl PartialEq<[u8]> for Rest<'_> {
    fn eq(&self, other: &[u8]) -> bool {
        self.buf == other
    }
}

impl<const N: usize> PartialEq<&[u8; N]> for Rest<'_> {
    fn eq(&self, other: &&[u8; N]) -> bool {
        self.buf == *other
    }
}

impl PartialEq<&[u8]> for Rest<'_> {
    fn eq(&self, other: &&[u8]) -> bool {
        self.buf == *other
    }
}

impl FieldAccess<RestMeta> {
    #[inline(always)]
    pub const fn meta() -> &'static dyn Meta {
        &RestMeta {}
    }
    #[inline(always)]
    pub const fn size_of_field_at(buf: &[u8]) -> usize {
        buf.len()
    }
    #[inline(always)]
    pub const fn extract(buf: &[u8]) -> Rest<'_> {
        Rest { buf }
    }
    #[inline(always)]
    pub const fn measure(buf: &[u8]) -> usize {
        buf.len()
    }
    #[inline(always)]
    pub fn copy_to_buf(buf: &mut BufWriter, value: &[u8]) {
        buf.write(value)
    }
}

/// A zero-terminated string.
#[allow(unused)]
pub struct ZTString<'a> {
    buf: &'a [u8],
}

field_access!(ZTStringMeta);
array_access!(ZTStringMeta);

pub struct ZTStringMeta {}
impl Meta for ZTStringMeta {
    fn name(&self) -> &'static str {
        "ZTString"
    }
}

impl Enliven for ZTStringMeta {
    type WithLifetime<'a> = ZTString<'a>;
    type ForMeasure<'a> = &'a str;
    type ForBuilder<'a> = &'a str;
}

impl std::fmt::Debug for ZTString<'_> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        String::from_utf8_lossy(self.buf).fmt(f)
    }
}

impl<'a> ZTString<'a> {
    pub fn to_owned(&self) -> Result<String, std::string::FromUtf8Error> {
        String::from_utf8(self.buf.to_owned())
    }

    pub fn to_str(&self) -> Result<&str, std::str::Utf8Error> {
        std::str::from_utf8(self.buf)
    }

    pub fn to_string_lossy(&self) -> std::borrow::Cow<'_, str> {
        String::from_utf8_lossy(self.buf)
    }
}

impl PartialEq for ZTString<'_> {
    fn eq(&self, other: &Self) -> bool {
        self.buf == other.buf
    }
}
impl Eq for ZTString<'_> {}

impl PartialEq<str> for ZTString<'_> {
    fn eq(&self, other: &str) -> bool {
        self.buf == other.as_bytes()
    }
}

impl PartialEq<&str> for ZTString<'_> {
    fn eq(&self, other: &&str) -> bool {
        self.buf == other.as_bytes()
    }
}

impl<'a> TryInto<&'a str> for ZTString<'a> {
    type Error = Utf8Error;
    fn try_into(self) -> Result<&'a str, Self::Error> {
        std::str::from_utf8(self.buf)
    }
}

impl FieldAccess<ZTStringMeta> {
    #[inline(always)]
    pub const fn meta() -> &'static dyn Meta {
        &ZTStringMeta {}
    }
    #[inline(always)]
    pub const fn size_of_field_at(buf: &[u8]) -> usize {
        let mut i = 0;
        loop {
            if buf[i] == 0 {
                return i + 1;
            }
            i += 1;
        }
    }
    #[inline(always)]
    pub const fn extract(buf: &[u8]) -> ZTString<'_> {
        let buf = buf.split_at(buf.len() - 1).0;
        ZTString { buf }
    }
    #[inline(always)]
    pub const fn measure(buf: &str) -> usize {
        buf.len() + 1
    }
    #[inline(always)]
    pub fn copy_to_buf(buf: &mut BufWriter, value: &str) {
        buf.write(value.as_bytes());
        buf.write_u8(0);
    }
    #[inline(always)]
    pub fn copy_to_buf_ref(buf: &mut BufWriter, value: &str) {
        buf.write(value.as_bytes());
        buf.write_u8(0);
    }
}

#[derive(Default, Debug, Clone, Copy, PartialEq, Eq)]
/// An encoded row value.
pub enum Encoded<'a> {
    #[default]
    Null,
    Value(&'a [u8]),
}

impl<'a> AsRef<Encoded<'a>> for Encoded<'a> {
    fn as_ref(&self) -> &Encoded<'a> {
        self
    }
}

field_access!(EncodedMeta);
array_access!(EncodedMeta);

pub struct EncodedMeta {}
impl Meta for EncodedMeta {
    fn name(&self) -> &'static str {
        "Encoded"
    }
}

impl Enliven for EncodedMeta {
    type WithLifetime<'a> = Encoded<'a>;
    type ForMeasure<'a> = Encoded<'a>;
    type ForBuilder<'a> = Encoded<'a>;
}

impl<'a> Encoded<'a> {}

impl PartialEq<str> for Encoded<'_> {
    fn eq(&self, other: &str) -> bool {
        self == &Encoded::Value(other.as_bytes())
    }
}

impl PartialEq<&str> for Encoded<'_> {
    fn eq(&self, other: &&str) -> bool {
        self == &Encoded::Value(other.as_bytes())
    }
}

impl PartialEq<[u8]> for Encoded<'_> {
    fn eq(&self, other: &[u8]) -> bool {
        self == &Encoded::Value(other)
    }
}

impl PartialEq<&[u8]> for Encoded<'_> {
    fn eq(&self, other: &&[u8]) -> bool {
        self == &Encoded::Value(other)
    }
}

impl FieldAccess<EncodedMeta> {
    #[inline(always)]
    pub const fn meta() -> &'static dyn Meta {
        &EncodedMeta {}
    }
    #[inline(always)]
    pub const fn size_of_field_at(buf: &[u8]) -> usize {
        const N: usize = std::mem::size_of::<i32>();
        if let Some(len) = buf.first_chunk::<N>() {
            let len = i32::from_be_bytes(*len);
            if len == -1 {
                N
            } else {
                len as usize + N
            }
        } else {
            panic!()
        }
    }
    #[inline(always)]
    pub const fn extract(buf: &[u8]) -> Encoded<'_> {
        const N: usize = std::mem::size_of::<i32>();
        if let Some((len, array)) = buf.split_first_chunk::<N>() {
            let len = i32::from_be_bytes(*len);
            if len == -1 {
                Encoded::Null
            } else {
                Encoded::Value(array)
            }
        } else {
            panic!()
        }
    }
    #[inline(always)]
    pub const fn measure(value: &Encoded) -> usize {
        match value {
            Encoded::Null => std::mem::size_of::<i32>(),
            Encoded::Value(value) => value.len() + std::mem::size_of::<i32>(),
        }
    }
    #[inline(always)]
    pub fn copy_to_buf(buf: &mut BufWriter, value: Encoded) {
        Self::copy_to_buf_ref(buf, &value)
    }
    #[inline(always)]
    pub fn copy_to_buf_ref(buf: &mut BufWriter, value: &Encoded) {
        match value {
            Encoded::Null => buf.write(&[0xff, 0xff, 0xff, 0xff]),
            Encoded::Value(value) => {
                let len: i32 = value.len() as _;
                buf.write(&len.to_be_bytes());
            }
        }
    }
}

// We alias usize here. Note that if this causes trouble in the future we can
// probably work around this by adding a new "const value" function to
// FieldAccess. For now it works!
pub struct LengthMeta(#[allow(unused)] i32);
impl Enliven for LengthMeta {
    type WithLifetime<'a> = usize;
    type ForMeasure<'a> = usize;
    type ForBuilder<'a> = usize;
}
impl Meta for LengthMeta {
    fn name(&self) -> &'static str {
        "len"
    }
}

impl FieldAccess<LengthMeta> {
    #[inline(always)]
    pub const fn meta() -> &'static dyn Meta {
        &LengthMeta(0)
    }
    #[inline(always)]
    pub const fn constant(value: usize) -> LengthMeta {
        LengthMeta(value as i32)
    }
    #[inline(always)]
    pub const fn size_of_field_at(buf: &[u8]) -> usize {
        FieldAccess::<i32>::size_of_field_at(buf)
    }
    #[inline(always)]
    pub const fn extract(buf: &[u8]) -> usize {
        FieldAccess::<i32>::extract(buf) as _
    }
    #[inline(always)]
    pub fn copy_to_buf(buf: &mut BufWriter, value: usize) {
        FieldAccess::<i32>::copy_to_buf(buf, value as i32)
    }
    #[inline(always)]
    pub fn copy_to_buf_rewind(buf: &mut BufWriter, rewind: usize, value: usize) {
        FieldAccess::<i32>::copy_to_buf_rewind(buf, rewind, value as i32)
    }
}

macro_rules! basic_types {
    ($($ty:ty)*) => {
        $(
        field_access!{$ty}

        impl Enliven for $ty {
            type WithLifetime<'a> = $ty;
            type ForMeasure<'a> = $ty;
            type ForBuilder<'a> = $ty;
        }

        impl <const S: usize> Enliven for [$ty; S] {
            type WithLifetime<'a> = [$ty; S];
            type ForMeasure<'a> = [$ty; S];
            type ForBuilder<'a> = [$ty; S];
        }

        #[allow(unused)]
        impl FieldAccess<$ty> {
            #[inline(always)]
            pub const fn meta() -> &'static dyn Meta {
                struct Meta {}
                impl $crate::protocol::Meta for Meta {
                    fn name(&self) -> &'static str {
                        stringify!($ty)
                    }
                }
                &Meta{}
            }
            #[inline(always)]
            pub const fn constant(value: usize) -> $ty {
                value as _
            }
            #[inline(always)]
            pub const fn size_of_field_at(_: &[u8]) -> usize {
                std::mem::size_of::<$ty>()
            }
            #[inline(always)]
            pub const fn extract(buf: &[u8]) -> $ty {
                if let Some(bytes) = buf.first_chunk() {
                    <$ty>::from_be_bytes(*bytes)
                } else {
                    panic!()
                }
            }
            #[inline(always)]
            pub fn copy_to_buf(buf: &mut BufWriter, value: $ty) {
                buf.write(&<$ty>::to_be_bytes(value));
            }
            #[inline(always)]
            pub fn copy_to_buf_rewind(buf: &mut BufWriter, rewind: usize, value: $ty) {
                buf.write_rewind(rewind, &<$ty>::to_be_bytes(value));
            }
        }

        #[allow(unused)]
        impl <const S: usize> FieldAccess<[$ty; S]> {
            #[inline(always)]
            pub const fn meta() -> &'static dyn Meta {
                struct Meta {}
                impl $crate::protocol::Meta for Meta {
                    fn name(&self) -> &'static str {
                        // TODO: can we extract this constant?
                        concat!('[', stringify!($ty), "; ", "S")
                    }
                }
                &Meta{}
            }
            #[inline(always)]
            pub const fn size_of_field_at(_buf: &[u8]) -> usize {
                std::mem::size_of::<$ty>() * S
            }
            #[inline(always)]
            pub const fn extract(mut buf: &[u8]) -> [$ty; S] {
                let mut out: [$ty; S] = [0; S];
                let mut i = 0;
                loop {
                    if i == S {
                        break;
                    }
                    (out[i], buf) = if let Some((bytes, rest)) = buf.split_first_chunk() {
                        (<$ty>::from_be_bytes(*bytes), rest)
                    } else {
                        panic!()
                    };
                    i += 1;
                }
                out
            }
            #[inline(always)]
            pub fn copy_to_buf(mut buf: &mut BufWriter, value: [$ty; S]) {
                if !buf.test(std::mem::size_of::<$ty>() * S) {
                    return;
                }
                for n in value {
                    buf.write(&<$ty>::to_be_bytes(n));
                }
            }
        }

        impl $crate::protocol::FixedSize for $ty {
            const SIZE: usize = std::mem::size_of::<$ty>();
        }
        impl <const S: usize> $crate::protocol::FixedSize for [$ty; S] {
            const SIZE: usize = std::mem::size_of::<$ty>() * S;
        }

        basic_types!(: array<$ty> u8 i16 i32);
        )*
    };

    (: array<$ty:ty> $($len:ty)*) => {
        $(
            #[allow(unused)]
            impl FieldAccess<ArrayMeta<$len, $ty>> {
                pub const fn meta() -> &'static dyn Meta {
                    &ArrayMeta::<$len, $ty> { _phantom: PhantomData }
                }
                #[inline(always)]
                pub const fn size_of_field_at(buf: &[u8]) -> usize {
                    const N: usize = std::mem::size_of::<$ty>();
                    const L: usize = std::mem::size_of::<$len>();
                    if let Some(len) = buf.first_chunk::<L>() {
                        (<$len>::from_be_bytes(*len) as usize * N + L)
                    } else {
                        panic!()
                    }
                }
                #[inline(always)]
                pub const fn extract(mut buf: &[u8]) -> Array<$len, $ty> {
                    const N: usize = std::mem::size_of::<$ty>();
                    const L: usize = std::mem::size_of::<$len>();
                    if let Some((len, array)) = buf.split_first_chunk::<L>() {
                        Array::new(array, <$len>::from_be_bytes(*len) as u32)
                    } else {
                        panic!()
                    }
                }
                #[inline(always)]
                pub const fn measure(buffer: &[$ty]) -> usize {
                    buffer.len() * std::mem::size_of::<$ty>() + std::mem::size_of::<$len>()
                }
                #[inline(always)]
                pub fn copy_to_buf(mut buf: &mut BufWriter, value: &[$ty]) {
                    let size: usize = std::mem::size_of::<$ty>() * value.len() + std::mem::size_of::<$len>();
                    if !buf.test(size) {
                        return;
                    }
                    buf.write(&<$len>::to_be_bytes(value.len() as _));
                    for n in value {
                        buf.write(&<$ty>::to_be_bytes(*n));
                    }
                }
            }
        )*
    }
}
basic_types!(u8 i16 i32);
