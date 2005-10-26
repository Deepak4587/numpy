import unittest
import sys
import copy

from scipy.test.testing import *
from scipy.base import array, typeinfo, alltrue, ndarray, asarray, can_cast,zeros
set_package_path()
from array_from_pyobj import wrap
del sys.path[0]

def flags_info(arr):
    flags = wrap.array_attrs(arr)[6]
    return flags2names(flags)

def flags2names(flags):
    info = []
    for flagname in ['CONTIGUOUS','FORTRAN','OWNDATA','ENSURECOPY',
                     'ENSUREARRAY','ALIGNED','NOTSWAPPED','WRITEABLE',
                     'UPDATEIFCOPY','BEHAVED_FLAGS','BEHAVED_FLAGS_RO',
                     'CARRAY_FLAGS','FARRAY_FLAGS'
                     ]:
        if abs(flags) & getattr(wrap,flagname):
            info.append(flagname)
    return info

class Intent:
    def __init__(self,intent_list=[]):
        self.intent_list = intent_list[:]
        flags = 0
        for i in intent_list:
            if i=='optional':
                flags |= wrap.F2PY_OPTIONAL
            else:
                flags |= getattr(wrap,'F2PY_INTENT_'+i.upper())
        self.flags = flags
    def __getattr__(self,name):
        name = name.lower()
        if name=='in_': name='in'
        return self.__class__(self.intent_list+[name])
    def __str__(self):
        return 'intent(%s)' % (','.join(self.intent_list))
    def __repr__(self):
        return 'Intent(%r)' % (self.intent_list)
    def is_intent(self,*names):
        for name in names:
            if name not in self.intent_list:
                return False
        return True
    def is_intent_exact(self,*names):
        return len(self.intent_list)==len(names) and self.is_intent(*names)

intent = Intent()

class Type(object):

    _type_names = ['BOOL','BYTE','UBYTE','SHORT','USHORT','INT','UINT',
                   'LONG','ULONG','LONGLONG','ULONGLONG',
                   'FLOAT','DOUBLE','LONGDOUBLE','CFLOAT','CDOUBLE',
                   'CLONGDOUBLE']
    _type_cache = {}

    _cast_dict = {'BOOL':['BOOL']}
    _cast_dict['BYTE'] = _cast_dict['BOOL'] + ['BYTE']
    _cast_dict['UBYTE'] = _cast_dict['BOOL'] + ['UBYTE']
    _cast_dict['BYTE'] = ['BYTE']
    _cast_dict['UBYTE'] = ['UBYTE']
    _cast_dict['SHORT'] = _cast_dict['BYTE'] + ['UBYTE','SHORT']
    _cast_dict['USHORT'] = _cast_dict['UBYTE'] + ['BYTE','USHORT']
    _cast_dict['INT'] = _cast_dict['SHORT'] + ['USHORT','INT']
    _cast_dict['UINT'] = _cast_dict['USHORT'] + ['SHORT','UINT']

    _cast_dict['LONG'] = _cast_dict['INT'] + ['LONG']
    _cast_dict['ULONG'] = _cast_dict['UINT'] + ['ULONG']

    _cast_dict['LONGLONG'] = _cast_dict['LONG'] + ['ULONG','LONGLONG']
    _cast_dict['ULONGLONG'] = _cast_dict['ULONG'] + ['LONG','ULONGLONG']

    _cast_dict['FLOAT'] = _cast_dict['SHORT'] + ['USHORT','FLOAT']
    _cast_dict['DOUBLE'] = _cast_dict['INT'] + ['UINT','FLOAT','DOUBLE']
    _cast_dict['LONGDOUBLE'] = _cast_dict['LONG'] + ['ULONG','FLOAT','DOUBLE','LONGDOUBLE']

    _cast_dict['CFLOAT'] = _cast_dict['FLOAT'] + ['CFLOAT']
    _cast_dict['CDOUBLE'] = _cast_dict['DOUBLE'] + ['CFLOAT','CDOUBLE']
    _cast_dict['CLONGDOUBLE'] = _cast_dict['LONGDOUBLE'] + ['CFLOAT','CDOUBLE','CLONGDOUBLE']
    
    
    def __new__(cls,name):
        if isinstance(name,type):
            dtype = name
            name = None
            for n,i in typeinfo.items():
                if isinstance(i,tuple) and dtype is i[-1]:
                    name = n
                    break
        obj = cls._type_cache.get(name.upper(),None)
        if obj is not None:
            return obj
        obj = object.__new__(cls)
        obj._init(name)
        cls._type_cache[name.upper()] = obj
        return obj
    
    def _init(self,name):
        self.NAME = name.upper()
        self.type_num = getattr(wrap,'PyArray_'+self.NAME)
        assert_equal(self.type_num,typeinfo[self.NAME][1])
        self.dtype = typeinfo[self.NAME][-1]
        self.elsize = typeinfo[self.NAME][2] / 8
        self.dtypechar = typeinfo[self.NAME][0]

    def cast_types(self):
        return map(self.__class__,self._cast_dict[self.NAME])

    def all_types(self):
        return map(self.__class__,self._type_names)

    def smaller_types(self):
        bits = typeinfo[self.NAME][3]
        types = []
        for name in self._type_names:
            if typeinfo[name][3]<bits:
                types.append(Type(name))
        return types

    def equal_types(self):
        bits = typeinfo[self.NAME][3]
        types = []
        for name in self._type_names:
            if name==self.NAME: continue
            if typeinfo[name][3]==bits:
                types.append(Type(name))
        return types

    def larger_types(self):
        bits = typeinfo[self.NAME][3]
        types = []
        for name in self._type_names:
            if typeinfo[name][3]>bits:
                types.append(Type(name))
        return types

class Array:
    def __init__(self,typ,dims,intent,obj):
        self.type = typ
        self.dims = dims
        self.intent = intent
        self.obj_copy = copy.deepcopy(obj)
        self.obj = obj

        # arr.dtypechar may be different from typ.dtypechar
        self.arr = wrap.call(typ.type_num,dims,intent.flags,obj)

        self.arr_attr = wrap.array_attrs(self.arr)

        if len(dims)>1:
            if self.intent.is_intent('c'):
                assert intent.flags & wrap.F2PY_INTENT_C
                assert not self.arr.flags['FORTRAN'],`self.arr.flags,obj.flags`
                assert self.arr.flags['CONTIGUOUS']
                assert not self.arr_attr[6] & wrap.FORTRAN
            else:
                assert not intent.flags & wrap.F2PY_INTENT_C
                assert self.arr.flags['FORTRAN']
                assert not self.arr.flags['CONTIGUOUS']
                assert self.arr_attr[6] & wrap.FORTRAN

        if obj is None:
            self.pyarr = None
            self.pyarr_attr = None
            return

        if intent.is_intent('cache'):
            assert isinstance(obj,ndarray),`type(obj)`
            self.pyarr = array(obj).reshape(*dims)
            
        else:
            self.pyarr = array(array(obj,
                                     dtype = typ.dtypechar).reshape(*dims),
                               fortran=not self.intent.is_intent('c'))
            assert self.pyarr.dtypechar==typ.dtypechar,\
                   `self.pyarr.dtypechar,typ.dtypechar`
        assert self.pyarr.flags['OWNDATA']
        self.pyarr_attr = wrap.array_attrs(self.pyarr)

        if len(dims)>1:
            if self.intent.is_intent('c'):
                assert not self.pyarr.flags['FORTRAN']
                assert self.pyarr.flags['CONTIGUOUS']
                assert not self.pyarr_attr[6] & wrap.FORTRAN
            else:
                assert self.pyarr.flags['FORTRAN']
                assert not self.pyarr.flags['CONTIGUOUS']
                assert self.pyarr_attr[6] & wrap.FORTRAN


        assert self.arr_attr[1]==self.pyarr_attr[1] # nd
        assert self.arr_attr[2]==self.pyarr_attr[2] # dimensions
        if self.arr_attr[1]<=1:
            assert self.arr_attr[3]==self.pyarr_attr[3],\
                   `self.arr_attr[3],self.pyarr_attr[3],self.arr.tostring(),self.pyarr.tostring()` # strides
        assert self.arr_attr[5][-2:]==self.pyarr_attr[5][-2:],\
               `self.arr_attr[5],self.pyarr_attr[5]` # descr
        assert self.arr_attr[6]==self.pyarr_attr[6],\
               `self.arr_attr[6],self.pyarr_attr[6],flags2names(0*self.arr_attr[6]-self.pyarr_attr[6]),flags2names(self.arr_attr[6]),intent` # flags

        if intent.is_intent('cache'):
            assert self.arr_attr[5][3]>=self.type.elsize,\
                   `self.arr_attr[5][3],self.type.elsize`
        else:
            assert self.arr_attr[5][3]==self.type.elsize,\
                   `self.arr_attr[5][3],self.type.elsize`
        assert self.arr_equal(self.pyarr,self.arr)
        
        if isinstance(self.obj,ndarray):
            if typ.elsize==Type(obj.dtype).elsize:
                if not intent.is_intent('copy') and self.arr_attr[1]<=1:
                    assert self.has_shared_memory()

    def arr_equal(self,arr1,arr2):
        if arr1.shape != arr2.shape:
            return False
        return alltrue(arr1==arr2)

    def __str__(self):
        return str(self.arr)

    def has_shared_memory(self):
        """Check that created array shares data with input array.
        """
        if self.obj is self.arr:
            return True
        if not isinstance(self.obj,ndarray):
            return False
        obj_attr = wrap.array_attrs(self.obj)
        return obj_attr[0]==self.arr_attr[0]

##################################################

class test_intent(unittest.TestCase):
    def check_in_out(self):
        assert_equal(str(intent.in_.out),'intent(in,out)')
        assert intent.in_.c.is_intent('c')
        assert not intent.in_.c.is_intent_exact('c')
        assert intent.in_.c.is_intent_exact('c','in')
        assert intent.in_.c.is_intent_exact('in','c')
        assert not intent.in_.is_intent('c')

class _test_shared_memory:
    num2seq = [1,2]
    num23seq = [[1,2,3],[4,5,6]]
    def check_in_from_2seq(self):
        a = self.array([2],intent.in_,self.num2seq)
        assert not a.has_shared_memory()

    def check_in_from_2casttype(self):
        for t in self.type.cast_types():
            obj = array(self.num2seq,dtype=t.dtype)
            a = self.array([len(self.num2seq)],intent.in_,obj)
            if t.elsize==self.type.elsize:
                assert a.has_shared_memory(),`self.type.dtype,t.dtype`
            else:
                assert not a.has_shared_memory(),`t.dtype`

    def check_inout_2seq(self):
        obj = array(self.num2seq,dtype=self.type.dtype)
        a = self.array([len(self.num2seq)],intent.inout,obj)
        assert a.has_shared_memory()

        try:
            a = self.array([2],intent.in_.inout,self.num2seq)
        except TypeError,msg:
            if not str(msg).startswith('failed to initialize intent(inout|inplace|cache) array'):
                raise
        else:
            raise SystemError,'intent(inout) should have failed on sequence'

    def check_f_inout_23seq(self):
        obj = array(self.num23seq,dtype=self.type.dtype,fortran=1)
        shape = (len(self.num23seq),len(self.num23seq[0]))
        a = self.array(shape,intent.in_.inout,obj)
        assert a.has_shared_memory()

        obj = array(self.num23seq,dtype=self.type.dtype,fortran=0)
        shape = (len(self.num23seq),len(self.num23seq[0]))
        try:
            a = self.array(shape,intent.in_.inout,obj)
        except ValueError,msg:
            if not str(msg).startswith('failed to initialize intent(inout) array'):
                raise
        else:
            raise SystemError,'intent(inout) should have failed on improper array'

    def check_c_inout_23seq(self):
        obj = array(self.num23seq,dtype=self.type.dtype)
        shape = (len(self.num23seq),len(self.num23seq[0]))
        a = self.array(shape,intent.in_.c.inout,obj)
        assert a.has_shared_memory()

    def check_in_copy_from_2casttype(self):
        for t in self.type.cast_types():
            obj = array(self.num2seq,dtype=t.dtype)
            a = self.array([len(self.num2seq)],intent.in_.copy,obj)
            assert not a.has_shared_memory(),`t.dtype`

    def check_c_in_from_23seq(self):
        a = self.array([len(self.num23seq),len(self.num23seq[0])],
                       intent.in_,self.num23seq)
        assert not a.has_shared_memory()

    def check_in_from_23casttype(self):
        for t in self.type.cast_types():
            obj = array(self.num23seq,dtype=t.dtype)
            a = self.array([len(self.num23seq),len(self.num23seq[0])],
                           intent.in_,obj)
            assert not a.has_shared_memory(),`t.dtype`

    def check_f_in_from_23casttype(self):
        for t in self.type.cast_types():
            obj = array(self.num23seq,dtype=t.dtype,fortran=1)
            a = self.array([len(self.num23seq),len(self.num23seq[0])],
                           intent.in_,obj)
            if t.elsize==self.type.elsize:
                assert a.has_shared_memory(),`t.dtype`
            else:
                assert not a.has_shared_memory(),`t.dtype`

    def check_c_in_from_23casttype(self):
        for t in self.type.cast_types():
            obj = array(self.num23seq,dtype=t.dtype)
            a = self.array([len(self.num23seq),len(self.num23seq[0])],
                           intent.in_.c,obj)
            if t.elsize==self.type.elsize:
                assert a.has_shared_memory(),`t.dtype`
            else:
                assert not a.has_shared_memory(),`t.dtype`

    def check_f_copy_in_from_23casttype(self):
        for t in self.type.cast_types():
            obj = array(self.num23seq,dtype=t.dtype,fortran=1)
            a = self.array([len(self.num23seq),len(self.num23seq[0])],
                           intent.in_.copy,obj)
            assert not a.has_shared_memory(),`t.dtype`

    def check_c_copy_in_from_23casttype(self):
        for t in self.type.cast_types():
            obj = array(self.num23seq,dtype=t.dtype)
            a = self.array([len(self.num23seq),len(self.num23seq[0])],
                           intent.in_.c.copy,obj)
            assert not a.has_shared_memory(),`t.dtype`

    def check_in_cache_from_2casttype(self):
        for t in self.type.all_types():
            if t.elsize != self.type.elsize:
                continue
            obj = array(self.num2seq,dtype=t.dtype)
            shape = (len(self.num2seq),)
            a = self.array(shape,intent.in_.c.cache,obj)        
            assert a.has_shared_memory(),`t.dtype`

            a = self.array(shape,intent.in_.cache,obj)        
            assert a.has_shared_memory(),`t.dtype`
            
            obj = array(self.num2seq,dtype=t.dtype,fortran=1)
            a = self.array(shape,intent.in_.c.cache,obj)        
            assert a.has_shared_memory(),`t.dtype`

            a = self.array(shape,intent.in_.cache,obj)
            assert a.has_shared_memory(),`t.dtype`

            try:
                a = self.array(shape,intent.in_.cache,obj[::-1])
            except ValueError,msg:
                if not str(msg).startswith('failed to initialize intent(cache) array'):
                    raise
            else:
                raise SystemError,'intent(cache) should have failed on multisegmented array'
    def check_in_cache_from_2casttype_failure(self):
        for t in self.type.all_types():
            if t.elsize >= self.type.elsize:
                continue
            obj = array(self.num2seq,dtype=t.dtype)
            shape = (len(self.num2seq),)
            try:
                a = self.array(shape,intent.in_.cache,obj)
            except ValueError,msg:
                if not str(msg).startswith('failed to initialize intent(cache) array'):
                    raise
            else:
                raise SystemError,'intent(cache) should have failed on smaller array'

    def check_cache_hidden(self):
        shape = (2,)
        a = self.array(shape,intent.cache.hide,None)
        assert a.arr.shape==shape

        shape = (2,3)
        a = self.array(shape,intent.cache.hide,None)
        assert a.arr.shape==shape

        shape = (-1,3)
        try:
            a = self.array(shape,intent.cache.hide,None)
        except ValueError,msg:
            if not str(msg).startswith('failed to create intent(cache|hide)|optional array'):
                raise
        else:
            raise SystemError,'intent(cache) should have failed on undefined dimensions'

    def check_hidden(self):
        shape = (2,)
        a = self.array(shape,intent.hide,None)
        assert a.arr.shape==shape
        assert a.arr_equal(a.arr,zeros(shape,dtype=self.type.dtype))

        shape = (2,3)
        a = self.array(shape,intent.hide,None)
        assert a.arr.shape==shape
        assert a.arr_equal(a.arr,zeros(shape,dtype=self.type.dtype))
        assert a.arr.flags['FORTRAN'] and not a.arr.flags['CONTIGUOUS']

        shape = (2,3)
        a = self.array(shape,intent.c.hide,None)
        assert a.arr.shape==shape
        assert a.arr_equal(a.arr,zeros(shape,dtype=self.type.dtype))
        assert not a.arr.flags['FORTRAN'] and a.arr.flags['CONTIGUOUS']

        shape = (-1,3)
        try:
            a = self.array(shape,intent.hide,None)
        except ValueError,msg:
            if not str(msg).startswith('failed to create intent(cache|hide)|optional array'):
                raise
        else:
            raise SystemError,'intent(hide) should have failed on undefined dimensions'

    def check_optional_none(self):
        shape = (2,)
        a = self.array(shape,intent.optional,None)
        assert a.arr.shape==shape
        assert a.arr_equal(a.arr,zeros(shape,dtype=self.type.dtype))

        shape = (2,3)
        a = self.array(shape,intent.optional,None)
        assert a.arr.shape==shape
        assert a.arr_equal(a.arr,zeros(shape,dtype=self.type.dtype))
        assert a.arr.flags['FORTRAN'] and not a.arr.flags['CONTIGUOUS']

        shape = (2,3)
        a = self.array(shape,intent.c.optional,None)
        assert a.arr.shape==shape
        assert a.arr_equal(a.arr,zeros(shape,dtype=self.type.dtype))
        assert not a.arr.flags['FORTRAN'] and a.arr.flags['CONTIGUOUS']

    def check_optional_from_2seq(self):
        obj = self.num2seq
        shape = (len(obj),)
        a = self.array(shape,intent.optional,obj)
        assert a.arr.shape==shape
        assert not a.has_shared_memory()

    def check_optional_from_23seq(self):
        obj = self.num23seq
        shape = (len(obj),len(obj[0]))
        a = self.array(shape,intent.optional,obj)
        assert a.arr.shape==shape
        assert not a.has_shared_memory()

        a = self.array(shape,intent.optional.c,obj)
        assert a.arr.shape==shape
        assert not a.has_shared_memory()

    def check_inplace(self):
        obj = array(self.num23seq,dtype=self.type.dtype)
        assert not obj.flags['FORTRAN'] and obj.flags['CONTIGUOUS']
        shape = obj.shape
        a = self.array(shape,intent.inplace,obj)
        assert obj[1][2]==a.arr[1][2],`obj,a.arr`
        a.arr[1][2]=54
        assert obj[1][2]==a.arr[1][2]==array(54,dtype=self.type.dtype),`obj,a.arr`
        assert a.arr is obj
        assert obj.flags['FORTRAN'] # obj attributes are changed inplace!
        assert not obj.flags['CONTIGUOUS']

    def check_inplace_from_casttype(self):
        for t in self.type.cast_types():
            if t is self.type:
                continue
            obj = array(self.num23seq,dtype=t.dtype)
            assert obj.dtype==t.dtype
            assert obj.dtype is not self.type.dtype
            assert not obj.flags['FORTRAN'] and obj.flags['CONTIGUOUS']
            shape = obj.shape
            a = self.array(shape,intent.inplace,obj)
            assert obj[1][2]==a.arr[1][2],`obj,a.arr`
            a.arr[1][2]=54
            assert obj[1][2]==a.arr[1][2]==array(54,dtype=self.type.dtype),`obj,a.arr`
            assert a.arr is obj
            assert obj.flags['FORTRAN'] # obj attributes are changed inplace!
            assert not obj.flags['CONTIGUOUS']
            assert obj.dtype is self.type.dtype # obj type is changed inplace!

for t in Type._type_names:
    exec '''\
class test_%s_gen(unittest.TestCase,
              _test_shared_memory
              ):
    type = Type(%r)
    array = lambda self,dims,intent,obj: Array(Type(%r),dims,intent,obj)
''' % (t,t,t)

if __name__ == "__main__":
    ScipyTest().run()
