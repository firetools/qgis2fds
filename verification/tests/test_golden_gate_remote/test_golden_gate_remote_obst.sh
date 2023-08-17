
qgis_process run "NIST FDS:Extract server layer" \
    --project_path="golden_gate_remote.qgs" \
    --distance_units=meters --area_units=m2 \
    --ellipsoid=EPSG:7030 \
    --chid=golden_gate_remote_obst \
    --fds_path="output" \
    --extent="-122.509448609,-122.467825037,37.817233198,37.849753575 [EPSG:4326]" \
    --pixel_size=30 \
    --dem_layer="dpiMode=7&identifier=landfire_wcs:LC20_Elev_220&url=https://edcintl.cr.usgs.gov/geoserver/landfire_wcs/us_topo/wcs" \
    --landuse_layer="dpiMode=7&identifier=landfire_wcs:LC22_F13_220&url=https://edcintl.cr.usgs.gov/geoserver/landfire_wcs/us_220/wcs" \
    --tex_pixel_size=1

qgis_process run "NIST FDS:Export FDS case" \
    --project_path="golden_gate_remote.qgs" \
    --distance_units=meters \
    --area_units=m2 \
    --ellipsoid=EPSG:7030 \
    --chid=golden_gate_remote_obst \
    --fds_path="output" \
    --extent="-122.509448609,-122.467825037,37.817233198,37.849753575 [EPSG:4326]" \
    --pixel_size=30 \
    --dem_layer="golden_gate_remote_obst_DEM_CLIPPED.tif" \
    --landuse_layer="golden_gate_remote_obst_LAND_CLIPPED.tif" \
    --landuse_type_filepath="Landfire.gov_F13.csv" \
    --fire_layer="data_layers/fire.gpkg" \
    --wind_filepath="wind.csv" \
    --tex_pixel_size=1 \
    --origin="-2279076.207440,1963675.963121 [EPSG:5070]" \
    --nmesh=4 \
    --cell_size=10 \
    --export_obst=true \
    --UtmGrid=TEMPORARY_OUTPUT \
    --ClippedDemLayer=TEMPORARY_OUTPUT \
    --UtmDemPoints=TEMPORARY_OUTPUT \
    --UtmInterpolatedDemLayer=TEMPORARY_OUTPUT \
    --ExtentDebug=TEMPORARY_OUTPUT \
    --dem_sampling=1

# Do not export texture
#   --tex_layer="crs=EPSG:3857&format&type=xyz&url=https://mt1.google.com/vt/lyrs%3Ds%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D&zmax=19&zmin=0" \

cd output
fds golden_gate_remote_obst.fds
smokeview -runscript golden_gate_remote_obst
cd ..

