#!/bin/bash
#BASE_DIR=../../qgis2fds.figures/baseline
#NEW_DIR=tests/test_out
#
#cd tests
#for TEST_NAME in *;
#do
#  if [ -d "${TEST_NAME}" ]; then
#    echo "${TEST_NAME}/output/*_s*.png"
#    echo "../${BASE_DIR:5}/TEST_NAME/"
#    cp ${TEST_NAME}/output/*_s*.png ../${BASE_DIR}/${TEST_NAME:5}/
#  fi
#done
cp tests/test_*/output/cern_meyrin_geom*_s*.png ../../qgis2fds.figures/baseline/cern_meyrin_geom/
cp tests/test_*/output/cern_meyrin_obst*_s*.png ../../qgis2fds.figures/baseline/cern_meyrin_obst/
cp tests/test_*/output/golden_gate_local_geom*_s*.png ../../qgis2fds.figures/baseline/golden_gate_local_geom/
cp tests/test_*/output/golden_gate_local_obst*_s*.png ../../qgis2fds.figures/baseline/golden_gate_local_obst/
cp tests/test_*/output/golden_gate_remote_geom*_s*.png ../../qgis2fds.figures/baseline/golden_gate_remote_geom/
cp tests/test_*/output/golden_gate_remote_obst*_s*.png ../../qgis2fds.figures/baseline/golden_gate_remote_obst/
