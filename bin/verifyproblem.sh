#!/usr/bin/env bash
#
# Wrapper script for running problemtools directly from within the
# problemtools repo without installing it on the system.  When
# installing problemtools on the system properly, this script should
# not be used.

exec "$(dirname "$(readlink -f "$0")")/.run_in_venv.sh" problemtools.verifyproblem "$@"
