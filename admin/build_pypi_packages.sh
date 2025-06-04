#!/bin/bash
set -e

ALLOW_DIRTY=false
TAG=develop

while getopts "d" opt; do
    case $opt in
        d) ALLOW_DIRTY=true ;;
        \?) echo "Invalid option: -$opt" ;;
    esac
done

shift $((OPTIND-1))

if [ "$1" != "" ]; then
    TAG=$1
fi

cd $(dirname $(readlink -f $0))

if ! ../venv/bin/twine -h > /dev/null 2> /dev/null; then
    echo "Did not find twine. Please run ../venv/bin/pip install twine"
    exit 1
fi

if [[ -n $(git status -s) ]]; then
    echo "Repository is dirty."
    git status -s
    [[ "${ALLOW_DIRTY}" != "true" ]] && exit 1
fi

if [[ $(git rev-parse --abbrev-ref HEAD) != ${TAG} && $(git describe --exact-match --tags 2>/dev/null) != ${TAG} ]]; then
    echo "Repository is currently not on branch/tag ${TAG}."
    [[ "${ALLOW_DIRTY}" != "true" ]] && exit 1
fi

echo "Building sdist and manylinux wheel"
sudo rm -rf ./pypi_dist
docker run --rm -v $(pwd)/..:/problemtools -v $(pwd)/pypi_dist:/dist quay.io/pypa/manylinux_2_28_x86_64 /bin/bash -c "
    yum -y install boost-devel gmp-devel ;
    mkdir /build ;
    cd /build ;
    git config --global --add safe.directory /problemtools/.git ;
    git clone /problemtools ;
    cd problemtools ;
    git checkout ${TAG} ;
    /opt/python/cp311-cp311/bin/python -m build ;
    auditwheel repair dist/problemtools-*.whl ;
    cp dist/*.tar.gz /dist ;
    cp wheelhouse/*.whl /dist"
sudo chown -R $USER:$USER pypi_dist

../venv/bin/twine check pypi_dist/*

echo "Running verifyproblem from wheel on all examples"
TEMPDIR=$(mktemp -d)
python3 -m venv "${TEMPDIR}"
"${TEMPDIR}/bin/pip" install pypi_dist/problemtools*manylinux*whl
shopt -s extglob
if ! "${TEMPDIR}/bin/verifyproblem" ../examples/!(README.md); then
    echo "Running verifyproblem on all examples failed. Please review output above to debug."
    rm -rf "${TEMPDIR}"
    exit 1
fi
rm -rf "${TEMPDIR}"

echo "Sucessfully built packages. If you're happy with them, upload:"
echo "    ../venv/bin/twine upload --verbose pypi_dist/*"
