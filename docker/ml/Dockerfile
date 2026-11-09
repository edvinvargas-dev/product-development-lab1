FROM tools_base
USER root
COPY requirements.in requirements.lock /opt/ml/
RUN python -m pip install --no-cache-dir --only-binary=:all: \
    -c /opt/requirements/tools.lock -r /opt/ml/requirements.lock \
    && python -m pip check
ENV OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
USER lab
