#!python

import numpy as np
import pandas as pd
import os.path

from _gui import  smartfilelist, pd_load_dataframe, pd_save_dataframe

gdal_formats = ['dxf', 'CAD', 'GeoJSON', 'kml','ESRI Shapefile']

def detect_ogr_driver(file_path):
  file_format = os.path.splitext(file_path.lower())[1]
  if file_format == '.json':
    file_format = "GeoJSON"
  #elif file_format == '.shp':
  #  file_format = "ESRI Shapefile"
  elif file_format == '.dwg':
    file_format = "CAD"
  elif len(file_format):
    file_format = file_format[1:]
  
  return file_format

def pd_save_gdal(df, output_path, layer_attribute = 'layer', driver_name = None):
  if driver_name is None:
    driver_name = detect_ogr_driver(output_path)
  
  if driver_name not in gdal_formats:
    if layer_attribute and layer_attribute != 'layer':
      df['layer'] = df[layer_attribute]
    return pd_save_dataframe(df, output_path)

  try:
    from osgeo import ogr
  except:
    return pd_save_dataframe(df, output_path)
  print("save using ogr driver", driver_name)

  import osgeo.osr as osr

  # use OGR specific exceptions
  ogr.UseExceptions()

  # Create the output
  dvr = ogr.GetDriverByName(driver_name)
  ods = dvr.CreateDataSource(output_path)
  poly = None
  lyr = ods.CreateLayer('')
  if lyr.TestCapability('CreateField'):
    if lyr.GetLayerDefn().GetFieldIndex('Layer') == -1:
      lyr.CreateField(ogr.FieldDefn('Layer', ogr.OFTString))
    for f in df.columns:
      if len(f) > 1:
        t = ogr.OFTString
        if df[f].dtype != np.object:
          t = ogr.OFTReal
        lyr.CreateField(ogr.FieldDefn(f, t))
  # start from the bottom of the dataframe to simplify polygon creation
  for row in df.index[::-1]:
    l = None
    if layer_attribute in df:
      l = df.loc[row, layer_attribute]
    if not l or (isinstance(l, float) and np.isnan(l)):
      l = os.path.splitext(os.path.basename(output_path))[0]

    n, x, y, z = df.loc[row, ['n','x','y','z']].astype(np.float)
    if poly is None:
      ptype = ''
      if 'type' in df:
        ptype = str.upper(df.loc[row, 'type'])
      print(ptype)
      if ptype.find('POINT') >= 0:
        poly = ogr.Geometry(ogr.wkbPointZM)
      elif ptype == 'LINEARRING' or ptype.find('POLY') >= 0:
        poly = ogr.Geometry(ogr.wkbLinearRing)
      else:
        poly = ogr.Geometry(ogr.wkbLineStringZM)

    poly.SetPoint(int(n), x, y, z)

    if n == 0.0:
      feature = ogr.Feature(lyr.GetLayerDefn())
      ffDefn = feature.GetDefnRef()
      for i in range(ffDefn.GetFieldCount()):
        f = ffDefn.GetFieldDefn(i).GetName()
        if f in df:
          feature.SetField(f, str(df.loc[row, f]))
        elif f.lower() in df:
          feature.SetField(f, df.loc[row, f.lower()])
      feature.SetField('Layer', l)
      feature.SetGeometry(poly)
      lyr.CreateFeature(feature)
      poly = None

def geometry_to_df(geometry):
  df = pd.DataFrame(columns=['x','y','z','t','n','type'])
  if geometry.GetPointCount():
    for n in range(geometry.GetPointCount()):
      df.loc[n, ['x','y','z']] = geometry.GetPoint(n)
      df.loc[n, 'w'] = 0
      df.loc[n, 't'] = bool(n)
      df.loc[n, 'n'] = n
      df.loc[n, 'type'] = geometry.GetGeometryName()
  else:
    for n in range(geometry.GetGeometryCount()):
      df = df.append(geometry_to_df(geometry.GetGeometryRef(n)), True)
  return(df)
    

def extract_geometry_points(rows, feature, geometry, layer = None):
  ffDefn = feature.GetDefnRef()

  if geometry.GetPointCount():
    for n in range(geometry.GetPointCount()):
      r = {}
      for i in range(ffDefn.GetFieldCount()):
        r[ffDefn.GetFieldDefn(i).GetName().lower()] = feature.GetField(i)
      r['type'] = geometry.GetGeometryName()
      r['t'] = bool(n)
      r['w'] = 0
      r['n'] = n
      r['x'],r['y'],r['z'] = geometry.GetPoint(n)
      if layer is not None:
        r['layer'] = layer
      rows.append(r)
  else:
    for n in range(geometry.GetGeometryCount()):
      extract_geometry_points(rows, feature, geometry.GetGeometryRef(n))

  return rows

def pd_extract_geometry_points(df, row, feature, geometry):
  print("# pd_extract_geometry_points", row)
  ffDefn = feature.GetDefnRef()

  if geometry.GetPointCount():
    for n in range(geometry.GetPointCount()):
      for i in range(ffDefn.GetFieldCount()):
        df.loc[row, ffDefn.GetFieldDefn(i).GetName().lower()] = feature.GetField(i)
      df.loc[row, 'type'] = geometry.GetGeometryName()
      df.loc[row, 't'] = bool(n)
      df.loc[row, 'w'] = 0
      df.loc[row, 'n'] = n
      df.loc[row, ['x','y','z']] = geometry.GetPoint(n)
      row += 1
  else:
    for n in range(geometry.GetGeometryCount()):
      row = pd_extract_geometry_points(df, row, feature, geometry.GetGeometryRef(n))

  return row

def pd_load_gdal(input_path, table_name = None, driver_name = None):
  if driver_name is None:
      driver_name = detect_ogr_driver(input_path)
  if driver_name not in gdal_formats:
    return pd_load_dataframe(input_path, '', table_name)

  # import OGR
  try:
    from osgeo import ogr
  except:
    return pd_load_dataframe(input_path, '', table_name)
  print("load using ogr driver", driver_name)
  import osgeo.osr as osr
  dvr = ogr.GetDriverByName(driver_name)

  ids = dvr.Open(input_path)

  if ids is None:
    raise Exception("Invalid input file or format")

  row = 0
  print("LayerCount", ids.GetLayerCount())
  rows = []
  for l in range(ids.GetLayerCount()):
    lyr = ids.GetLayer(l)
    lyrDefn = lyr.GetLayerDefn()
    layer = lyr.GetName()
    print("layer", layer)

    for feature in lyr:
      extract_geometry_points(rows, feature, feature.GetGeometryRef(), layer)
  df = pd.DataFrame.from_records(rows)
  
  df['layer'] = lyr.GetName()
  return df
