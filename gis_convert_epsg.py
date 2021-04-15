#!python
# Copyright 2019 Vale
# convert the coordinate reference system
# input_path: path to input file in a supported format
# x: field with x/longitude
# y: field with y/latitude
# z: (optional) field with z/elevation
# convert_clock_to_decimal: convert H*M'S"D to decimal
# convert_lookup: use a column on the data to define a srs for each point before using global srs
# srs_column: the column with raw information about which srs to use
# srs_lookup: a table used to match raw column data to a actual srs
# custom_systems: enable to select a zip with information on custom reference systems
# srs_input: epsg code or WKT/PROJ file of the source coordinate system
# srs_output: epsg code or WKT/PROJ file of desired output coordinate system
# output_path: path to save converted file
# v1.0 07/2019 paulo.ernesto
# License: Apache 2.0
# https://github.com/pemn/gis_convert_epsg
# https://spatialreference.org/ref/epsg/
'''
usage: $0 input_path*csv,xlsx,dxf,dwg,shp,kml,msh,obj,00t,dgd.isis,tif,tiff x:input_path y:input_path z:input_path convert_clock_to_decimal@ convert_lookup@2 srs_column:input_path srs_lookup*csv,xlsx custom_systems_enable@1 custom_systems_zip*zip srs_input:custom_systems_zip srs_output:custom_systems_zip output_path*csv,xlsx,dxf,dwg,shp,kml,msh,obj,00t,dgd.isis,tif,tiff
'''

import sys, os.path
import numpy as np
import pandas as pd
import re
import time

# import modules from a pyz (zip) file with same name as scripts
sys.path.insert(0, os.path.splitext(sys.argv[0])[0] + '.pyz')

from _gui import usage_gui, pd_load_dataframe, pd_save_dataframe, pyd_zip_extract

pyd_zip_extract()

#from pd_gdal import pd_load_gdal, pd_save_gdal
import pyproj

def gis_create_prj(output_path, srs):
  prj_path = os.path.splitext(output_path)[0] + '.prj'
  print("creating file", prj_path)
  file = open(prj_path, 'w')
  p = pyproj.crs.CRS(sanitize_srs(srs))
  file.write(p.to_wkt(pyproj.enums.WktVersion.WKT1_ESRI))
  file.close()

def sanitize_srs(srs, recurse=False):
  if (isinstance(srs, str) and srs.isnumeric()) or not isinstance(srs, str):
    srs = "epsg:" + str(srs)
  elif('+' in srs):
    srs = list(map(sanitize_srs,srs.split('+')))
    if not recurse:
      srs = srs[0]
  elif('=' in srs):
    srs = 'proj=affine ' + srs
  elif(re.search(r'\.(wkt|prj)$', srs, re.IGNORECASE)):
    srs = open(srs).read()

  return srs

def prj_check_plus(t, sr1, sr2):
  p1l = sanitize_srs(sr1, True)
  p2l = sanitize_srs(sr2, True)
  pipeline = t.definition.split()
  flag = False
  if isinstance(p1l, list):
    flag = True
    pipeline.insert(1, 'step')
    pipeline.insert(1, 'inv')
    for i in range(1,len(p1l)):
      pipeline.insert(1, p1l[i])
  
  if isinstance(p2l, list):
    flag = True
    pipeline.append('step')
    for i in range(1,len(p2l)):
      pipeline.append(p2l[i])
  if flag:
    pipeline = chr(10).join(pipeline)
    print(pipeline)
    t = pyproj.Transformer.from_pipeline(pipeline)
  return t

def gis_project_df(df, in_sr, out_sr, x = 'x', y = 'y', z = 'z'):
  """ project points stored in a dataframe from a coordinate system to another """
  print("pyproj",pyproj.__version__)
  import shapely.geometry
  c = time.time()

  if not str(df.index.dtype).startswith('int'):
    df.reset_index(inplace=True)
  xyz = [x,y,z]
  if z not in df:
    df[z] = 0

  if "SHAPE" in df:
    df[x] = np.nan
    df[y] = np.nan
    df[z] = np.nan
    for row in df.index:
      shape = df.loc[row, 'SHAPE']
      if shape is None:
        continue
      # restore serialized shape
      if df.dtypes['SHAPE'] == 'object':
        shape = shapely.geometry.Point(eval(shape))
      df.loc[row, xyz] = shape.coordinates()

  xyz1 = df[xyz].values
  
  p1 = pyproj.Proj(sanitize_srs(in_sr))
  p2 = pyproj.Proj(sanitize_srs(out_sr))
  t = pyproj.Transformer.from_proj(p1, p2, always_xy=True)
  t = prj_check_plus(t, in_sr, out_sr)
  xyz2 = t.transform(xyz1[:, 0], xyz1[:, 1], xyz1[:, 2])
  df[xyz] = np.transpose(xyz2)

  if 'EPSG' in df:
    print(out_sr)
    out_epsg = out_sr
    if not isinstance(out_sr, int):
      try:
        out_epsg = pyproj.crs.CRS(sanitize_srs(out_sr)).to_epsg()
      except:
        out_epsg = None

    print('Converting EPSG code from',df['EPSG'].max(),'to',out_epsg)
    df['EPSG'] = out_epsg
  print("gis_project_df profile time",time.time() - c)
  return df

def clock_to_decimal(vc):
  m = re.search(r'(\d+).*[°º](\d*)[\'’]?(\d*)"?(\w*)', vc)
  vd = np.nan
  if m:
    g = m.groups(0)
    if g[0].isnumeric():
      vd = float(g[0])
    else:
      return vd
    if g[1].isnumeric():
      vd += float(g[1]) / 60
    if g[2].isnumeric():
      vd += float(g[2]) / 360
    
    d = str(g[3]).lower()
    if 'w' in d or 's' in d:
      vd *= -1
  
  return vd

def gis_convert_epsg(input_path, x, y, z, convert_clock_to_decimal, convert_lookup, srs_column, srs_lookup, custom_systems_enable, custom_systems_zip, srs_input, srs_output, output_path):
  print("# gis_convert_epsg")
  if len(x) == 0:
    x = 'x'
  if len(y) == 0:
    y = 'y'
  if len(z) == 0:
    z = 'z'

  df = pd_load_dataframe(input_path)

  if int(convert_clock_to_decimal):
    for row in df.index:
      for col in [x, y]:
        vc = df.loc[row, col]
        vd = clock_to_decimal(vc)
        print(row,vc,"=>",vd)
        df.loc[row, col] = vd
  
  if int(convert_lookup):
    df_lookup = pd_load_dataframe(srs_lookup)
    df_lookup.set_index(df_lookup.columns[0], inplace=True)
    for raw_srs in df[srs_column].unique():
      srs_input_row = None
      # check this row has a specific srs which is on the lookup table
      if raw_srs in df_lookup.index:
        srs_input_row = df_lookup.at[raw_srs, df_lookup.columns[0]]
      else:
        srs_input_row = sanitize_srs(raw_srs)
        if srs_input_row is None and srs_input:
          # rows that do not have a valid srs, default to the global epsg
          srs_input_row = srs_input
      print(raw_srs,srs_input_row)
      if srs_input_row is not None:
        df.update(gis_project_df(df.loc[df[srs_column] == raw_srs].copy(), srs_input_row, srs_output, x, y, z))

  else:
    # global conversion
    if int(custom_systems_enable):
      from zipfile import ZipFile
      zf = ZipFile(custom_systems_zip)
      for f in (srs_input, srs_output):
        if f in zf.namelist():
          print(f)
          zf.extract(f)
      zf.close()
    
    df = gis_project_df(df, srs_input, srs_output, x, y, z)

  if output_path:
    pd_save_dataframe(df, output_path)
    if output_path.lower().endswith('shp'):
      gis_create_prj(output_path, srs_output)
  else:
    print(df)

  print("# gis_convert_epsg finished")

main = gis_convert_epsg

if __name__=="__main__":
  usage_gui(__doc__)
