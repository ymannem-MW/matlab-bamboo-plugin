FROM maven:3.9.9-eclipse-temurin-21

ENV DEBIAN_FRONTEND=noninteractive

ARG INSTALL_MATLAB=false
ARG MATLAB_RELEASE=R2026a
ARG MATLAB_PRODUCTS="MATLAB"
ARG MATLAB_INSTALL_ROOT=/opt/matlab
ARG MATLAB_BATCH_ADAPTER_ROOT=/opt/matlab-batch-adapter

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        fontconfig \
        git \
        libatomic1 \
        libasound2t64 \
        libgbm1 \
        libgl1 \
        libglib2.0-0 \
        libglu1-mesa \
        libgtk-3-0 \
        libnss3 \
        libx11-6 \
        libxcomposite1 \
        libxext6 \
        libxi6 \
        libxrandr2 \
        libxrender1 \
        libxss1 \
        libxt6 \
        libxtst6 \
        lsof \
        procps \
        python3 \
        python3-requests \
        unzip \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN if [ "${INSTALL_MATLAB}" = "true" ]; then \
        matlab_destination="${MATLAB_INSTALL_ROOT}/${MATLAB_RELEASE}" \
        && mkdir -p "${matlab_destination}" \
        && curl -fsSL -o /tmp/mpm "https://www.mathworks.com/mpm/glnxa64/mpm" \
        && chmod +x /tmp/mpm \
        && /tmp/mpm install \
            --release="${MATLAB_RELEASE}" \
            --destination="${matlab_destination}" \
            --products ${MATLAB_PRODUCTS} \
        && rm -f /tmp/mpm; \
    fi

RUN curl -fsSL -o /tmp/install-matlab-batch.sh \
        "https://raw.githubusercontent.com/mathworks-ref-arch/matlab-dockerfile/main/alternates/non-interactive/install/install-matlab-batch.sh" \
    && bash /tmp/install-matlab-batch.sh \
    && rm -f /tmp/install-matlab-batch.sh

COPY matlab-batch-adapter.sh /usr/local/bin/matlab-batch-adapter

RUN if [ "${INSTALL_MATLAB}" = "true" ]; then \
        matlab_destination="${MATLAB_INSTALL_ROOT}/${MATLAB_RELEASE}" \
        && mkdir -p "${MATLAB_BATCH_ADAPTER_ROOT}/bin" \
        && cp "${matlab_destination}/VersionInfo.xml" "${MATLAB_BATCH_ADAPTER_ROOT}/VersionInfo.xml" \
        && cp /usr/local/bin/matlab-batch-adapter "${MATLAB_BATCH_ADAPTER_ROOT}/bin/matlab" \
        && chmod +x /usr/local/bin/matlab-batch-adapter "${MATLAB_BATCH_ADAPTER_ROOT}/bin/matlab"; \
    fi

WORKDIR /workspace/matlab-bamboo-plugin/systemtest

CMD ["python3", "-u", "run_system_tests.py"]
