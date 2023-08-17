#!/usr/bin/env bash

cd tests/test_cern_meyrin
bash test_cern_meyrin_geom.sh
bash test_cern_meyrin_obst.sh
cd ../..

cd tests/test_golden_gate_local
bash test_golden_gate_local_geom.sh
bash test_golden_gate_local_obst.sh
cd ../..

cd tests/test_golden_gate_remote
bash test_golden_gate_remote_geom.sh
bash test_golden_gate_remote_obst.sh
cd ../..
