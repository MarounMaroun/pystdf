import sys

import struct
import re

from PySTDF.Types import *
from PySTDF import V4

from PySTDF.Pipeline import DataSource

def appendFieldParser(fn, action):
  """Append a field parsing function to a record parsing function.
  This is used to build record parsing functions based on the record type specification."""
  def newRecordParser(*args):
    fields = fn(*args)
    try:
      fields.append(action(*args))
    except EndOfRecordException: pass
    return fields
  return newRecordParser

class Parser(DataSource):
  def readAndUnpack(self, header, fmt):
    size = struct.calcsize(fmt)
    if (size > header.len):
      self.inp.read(header.len)
      header.len = 0
      raise EndOfRecordException()
    buf = self.inp.read(size)
    if len(buf) == 0:
      self.eof = 1
      raise EofException()
    header.len -= len(buf)
    val,=struct.unpack(self.endian + fmt, buf)
    return val
  
  def readAndUnpackDirect(self, fmt):
    size = struct.calcsize(fmt)
    buf = self.inp.read(size)
    if len(buf) == 0:
      self.eof = 1
      raise EofException()
    val,=struct.unpack(self.endian + fmt, buf)
    return val
  
  def readField(self, header, stdfFmt):
    return self.readAndUnpack(header, packFormatMap[stdfFmt])
  
  def readFieldDirect(self, stdfFmt):
    return self.readAndUnpackDirect(packFormatMap[stdfFmt])
  
  def readCn(self, header):
    if header.len == 0:
      raise EndOfRecordException()
    slen = self.readField(header, "U1")
    if slen > header.len:
      self.inp.read(header.len)
      header.len = 0
      raise EndOfRecordException()
    if slen == 0:
      return ""
    buf = self.inp.read(slen);
    if len(buf) == 0:
      self.eof = 1
      raise EofException()
    header.len -= len(buf)
    val,=struct.unpack(str(slen) + "s", buf)
    return val
  
  def readBn(self, header):
    blen = self.readField(header, "U1")
    bn = []
    for i in range(0, blen):
      bn.append(readField(header, "B1"))
    return bn
  
  def readDn(self, header):
    dbitlen = self.readField(header, "U2")
    dlen = dbitlen / 8
    if dbitlen % 8 > 0:
      dlen+=1
    dn = []
    for i in range(0, dlen):
      dn.append(self.readField(header, "B1"))
    return dn
  
  def readVn(self, header):
    vlen = self.readField(header, "U2")
    vn = []
    for i in range(0, vlen):
      fldtype = self.readField(header, "B1")
      if self.vnMap.has_key(fldtype):
        vn.append(self.vnMap[fldtype](header))
    return vn
  
  def readArray(self, header, indexValue, stdfFmt):
    if (stdfFmt == 'N1'):
      self.readArray(header, indexValue/2+indexValue%2, 'U1')
      return
    arr = []
    for i in range(indexValue):
      arr.append(self.unpackMap[stdfFmt](header, stdfFmt))
    return arr
  
  def readHeader(self):
    hdr = RecordHeader()
    hdr.len = self.readFieldDirect("U2")
    hdr.typ = self.readFieldDirect("U1")
    hdr.sub = self.readFieldDirect("U1")
    return hdr
  
  def _detectEndian(self):
    self.eof = 0
    header = self.readHeader()
    if header.typ != 0 and header.sub != 10:
      raise InitialSequenceException()
    cpuType = self.readFieldDirect("U1")
    if self.reopen_fn:
      self.inp = self.reopen_fn()
    else:
      self.inp.seek(0)
    if cpuType == 2:
      return '<'
    else:
      return '>'
  
  def header(self, header): pass
  
  def parse(self):
    self.begin()
    
    try:
      saveEndian = self.endian
      if self.endian == None:
        self.endian = '@'
        self.endian = self._detectEndian()
      
      self.eof = 0
      fields = None
      try:
        while self.eof==0:
          header = self.readHeader()
          self.header(header)
          if (self.recordMap.has_key((header.typ, header.sub))):
            recType = self.recordMap[(header.typ, header.sub)]
            recParser = self.recordParsers[(header.typ, header.sub)]
            fields = recParser(self, header, [])
            if len(fields) < len(recType.columnNames):
              fields += [None] * (len(recType.columnNames) - len(fields))
            self.send((recType, fields))
          else:
            self.inp.read(header.len)
      except EofException: pass
      self.endian = saveEndian
      self.complete()
    except Exception, exception:
      self.cancel()
      raise
  
  def getFieldParser(self, fieldType):
    if (fieldType.startswith("k")):
      fieldIndex, arrayFmt = re.match('k(\d+)([A-Z][a-z0-9]+)', fieldType).groups()
      return lambda self, header, fields: self.readArray(header, fields[int(fieldIndex)], arrayFmt)
    else:
      parseFn = self.unpackMap[fieldType]
      return lambda self, header, fields: parseFn(header, fieldType)
  
  def createRecordParser(self, recType):
    fn = lambda self, header, fields: fields
    for stdfType in recType.fieldStdfTypes:
      fn = appendFieldParser(fn, self.getFieldParser(stdfType))
    return fn
  
  def __init__(self, recTypes=V4.Records, inp=sys.stdin, reopen_fn=None, endian=None):
    DataSource.__init__(self, ['header']);
    self.eof = 1
    self.recTypes = set(recTypes)
    self.inp = inp
    self.reopen_fn = reopen_fn
    self.endian = endian
    
    self.recordMap = dict(
      [ ( (recType.typ, recType.sub), recType )
        for recType in recTypes ])
    
    self.unpackMap = {
      "C1": self.readField,
      "B1": self.readField,
      "U1": self.readField,
      "U2": self.readField,
      "U4": self.readField,
      "U8": self.readField,
      "I1": self.readField,
      "I2": self.readField,
      "I4": self.readField,
      "I8": self.readField,
      "R4": self.readField,
      "R8": self.readField,
      "Cn": lambda header, fmt: self.readCn(header),
      "Bn": lambda header, fmt: self.readBn(header),
      "Dn": lambda header, fmt: self.readDn(header),
      "Vn": lambda header, fmt: self.readVn(header)
    }
    
    self.recordParsers = dict(
      [ ( (recType.typ, recType.sub), self.createRecordParser(recType) )
        for recType in recTypes ])
    
    self.vnMap = {
      0: lambda header: self.inp.read(header, 1),
      1: lambda header: self.readField(header, "U1"),
      2: lambda header: self.readField(header, "U2"),
      3: lambda header: self.readField(header, "U4"),
      4: lambda header: self.readField(header, "I1"),
      5: lambda header: self.readField(header, "I2"),
      6: lambda header: self.readField(header, "I4"),
      7: lambda header: self.readField(header, "R4"),
      8: lambda header: self.readField(header, "R8"),
      10: lambda header: self.readCn(header),
      11: lambda header: self.readBn(header),
      12: lambda header: self.readDn(header),
      13: lambda header: self.readField(header, "U1")
    }
