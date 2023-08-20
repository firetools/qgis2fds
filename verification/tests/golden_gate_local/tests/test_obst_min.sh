#!/usr/bin/env bash

# Clean

rm -f ../FDS/*  # does not rm .gitignore

# Run QGIS

cd ../QGIS
CHID=$(basename "$0" ".sh")
qgis_process run 'NIST FDS:Export FDS case' \
    --project_path="golden_gate_local.qgs" \
    --distance_units=meters \
    --area_units=m2 \
    --ellipsoid=EPSG:7019 \
    --chid="$CHID" \
    --fds_path='../FDS' \
    --extent='-122.491206899,-122.481181391,37.827810126,37.833676214 [EPSG:4326]' \
    --pixel_size=10 \
    --dem_layer='layers/US_DEM2016_local.tif' \
    --export_obst=true \
    --UtmGrid=TEMPORARY_OUTPUT \
    --UtmDemPoints=TEMPORARY_OUTPUT \
    --UtmInterpolatedDemLayer=TEMPORARY_OUTPUT \
    --ExtentDebug=TEMPORARY_OUTPUT

# Run FDS

cd ../FDS

cat << EOF > "$CHID.ini"
VIEWPOINT5
 0 -4 3
 0.500000 -1.533945 0.092708 1.000000 2
 0.000000 0.000000 90.000000 0
 0.500000 0.452000 0.092708
 -33.000000 32.000000
 1.000000 0.000000 0.000000 0.000000
 0.000000 1.000000 0.000000 0.000000
 0.000000 0.000000 1.000000 0.000000
 0.000000 0.000000 0.000000 1.000000
 0 0 0 0 0 0 0
 -62.159824 -56.685352 429.114441 63.090176 56.540646 463.304108
 iso
EOF

cat << EOF > "$CHID.ssf"
SETVIEWPOINT
 ZMAX
RENDERDOUBLEONCE
 
SETVIEWPOINT
 ZMIN
RENDERDOUBLEONCE
 
SETVIEWPOINT
 YMAX
RENDERDOUBLEONCE
 
SETVIEWPOINT
 YMIN
RENDERDOUBLEONCE
 
SETVIEWPOINT
 XMAX
RENDERDOUBLEONCE
 
SETVIEWPOINT
 XMIN
RENDERDOUBLEONCE
 
SETVIEWPOINT
 iso
RENDERDOUBLEONCE
EOF

fds "$CHID.fds"
smokeview -runscript "$CHID"
