#!/usr/bin/env bash

cd tests/test_cern_meyrin/output
fds cern_meyrin_geom.fds
fds cern_meyrin_obst.fds
smokeview cern_meyrin_geom
smokeview cern_meyrin_obst
cd ../../..

cd tests/test_golden_gate_local/output
fds golden_gate_local_geom.fds
fds golden_gate_local_obst.fds
smokeview golden_gate_local_geom
smokeview golden_gate_local_obst
cd ../../..

cd tests/test_golden_gate_remote/output
fds golden_gate_remote_geom.fds
fds golden_gate_remote_obst.fds
smokeview golden_gate_remote_geom
smokeview golden_gate_remote_obst
cd ../../..
