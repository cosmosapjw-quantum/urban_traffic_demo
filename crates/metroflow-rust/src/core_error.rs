//! Scientific computation errors; Python exception conversion is exclusively a frontend adapter.
use std::fmt;
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum ErrorKind { Value, Resource, Arithmetic, Io, Index }
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct CoreError {pub kind:ErrorKind,pub message:String}
pub type CoreResult<T> = Result<T,CoreError>;
impl CoreError {
    pub fn value(s:impl Into<String>)->Self{Self{kind:ErrorKind::Value,message:s.into()}}
    pub fn resource(s:impl Into<String>)->Self{Self{kind:ErrorKind::Resource,message:s.into()}}
    pub fn arithmetic(s:impl Into<String>)->Self{Self{kind:ErrorKind::Arithmetic,message:s.into()}}
    pub fn io(s:impl Into<String>)->Self{Self{kind:ErrorKind::Io,message:s.into()}}
    pub fn index(s:impl Into<String>)->Self{Self{kind:ErrorKind::Index,message:s.into()}}
}
impl fmt::Display for CoreError{
    fn fmt(&self,f:&mut fmt::Formatter<'_>)->fmt::Result{write!(f,"{}",self.message)}
}
impl std::error::Error for CoreError{}
#[cfg(feature="python-extension")]
impl From<CoreError> for pyo3::PyErr {
    fn from(e:CoreError)->Self{
        use pyo3::exceptions::*;
        match e.kind{
            ErrorKind::Value=>PyValueError::new_err(e.message),
            ErrorKind::Resource=>PyMemoryError::new_err(e.message),
            ErrorKind::Arithmetic=>PyArithmeticError::new_err(e.message),
            ErrorKind::Io=>PyIOError::new_err(e.message),
            ErrorKind::Index=>PyIndexError::new_err(e.message),
        }
    }
}
