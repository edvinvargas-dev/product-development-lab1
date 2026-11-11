FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 lab

ARG REQUIREMENTS_FILE=tools.lock
COPY requirements/ /opt/requirements/
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r /opt/requirements/${REQUIREMENTS_FILE} \
    && python -m pip check

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DVC_NO_ANALYTICS=1
USER lab
WORKDIR /workspace
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
