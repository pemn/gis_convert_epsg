#!python
# Copyright 2019 Vale
# convert the coordinate reference system
# input_path: path to input file in a supported format
# x: field with x/longitude
# y: field with y/latitude
# convert_clock_to_decimal: convert H*M'S"D to decimal
# convert_lookup: use a column on the data to define a srs for each point before using global srs
# srs_column: the column with raw information about which srs to use
# srs_lookup: a table used to match raw column data to a actual srs
# https://spatialreference.org/ref/epsg/
# srs_input: epsg code or WKT file of the source coordinate system
# srs_output: epsg code or WKT file of desired output coordinate system
# output_path: path to save converted file
# v1.0 07/2019 paulo.ernesto
'''
usage: $0 input_path*csv,xlsx,dgd.isis,00t x:input_path y:input_path convert_clock_to_decimal@ convert_lookup@2 srs_column:input_path srs_lookup*csv,xlsx srs_input*wkt,prj srs_output*wkt,prj output_path*csv,xlsx,00t,dgd.isis
'''

import sys, os.path
import numpy as np
import pandas as pd
import re

# import modules from a pyz (zip) file with same name as scripts
sys.path.insert(0, os.path.splitext(sys.argv[0])[0] + '.pyz')

from _gui import usage_gui, pd_load_dataframe, pd_save_dataframe, pyd_zip_extract

pyd_zip_extract()

def sanitize_srs(srs):
  if not isinstance(srs, str) or srs.isnumeric():
    srs = "epsg:" + str(srs)
  elif(re.search(r'\.(wkt|prj)$', srs, re.IGNORECASE)):
    srs = open(srs).read()
  else:
    srs = None
  return srs

def gis_project_df(df, in_sr, out_sr, x = 'x', y = 'y'):
  """ project points stored in a dataframe from a coordinate system to another """
  print("gis_project_df")
  import pyproj
  import shapely.geometry

  p1 = pyproj.Proj(sanitize_srs(in_sr))
  p2 = pyproj.Proj(sanitize_srs(out_sr))

  if "SHAPE" in df:
    df[x] = np.nan
    df[y] = np.nan

  if not df.index.dtype_str.startswith('int'):
    df.reset_index(inplace=True)

  for row in df.index:
    xyz1 = None
    if "SHAPE" in df:
      shape = df.loc[row, 'SHAPE']
      if shape is None:
        continue
      # restore serialized shape
      if df.dtypes['SHAPE'] == 'object':
        shape = shapely.geometry.Point(eval(shape))
      xyz1 = shape.coordinates()

    elif y in df:
      xyz1 = df.loc[row, [x,y]].astype(np.float_)
    else:
      break

    xyz2 = pyproj.transform(p1, p2, xyz1[0], xyz1[1])

    print(row, in_sr, tuple(xyz1), out_sr, xyz2)
    df.loc[row, [x,y]] = xyz2

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

def gis_convert_epsg(input_path, x, y, convert_clock_to_decimal, convert_lookup, srs_column, srs_lookup, srs_input, srs_output, output_path):
  print("# gis_convert_epsg")

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
        df.update(gis_project_df(df.loc[df[srs_column] == raw_srs].copy(), srs_input_row, srs_output, x, y))

  else:
    # global conversion
    df = gis_project_df(df, srs_input, srs_output, x, y)

  pd_save_dataframe(df, output_path)

  print("finished")

main = gis_convert_epsg

if __name__=="__main__":
  usage_gui(__doc__)
