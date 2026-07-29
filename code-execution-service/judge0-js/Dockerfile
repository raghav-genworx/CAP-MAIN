# syntax=docker/dockerfile:1

FROM ruby:2.7.8-slim-bullseye

ARG DEBIAN_FRONTEND=noninteractive
ARG JUDGE0_REF=v1.13.1
ARG NODE_VERSION=22.17.1
ARG TARGETARCH

ENV RAILS_ENV=production \
    RACK_ENV=production \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8 \
    BOX_ROOT=/var/local/lib/isolate \
    JUDGE0_VERSION=${JUDGE0_REF} \
    NODE_VERSION=${NODE_VERSION}

RUN set -eux; \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      bash \
      build-essential \
      ca-certificates \
      cron \
      curl \
      g++ \
      gcc \
      libcap-dev \
      libpq-dev \
      locales \
      openjdk-11-jdk-headless \
      procps \
      python3 \
      shared-mime-info \
      sudo \
      xz-utils; \
    rm -rf /var/lib/apt/lists/*; \
    echo "en_US.UTF-8 UTF-8" > /etc/locale.gen; \
    locale-gen

RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
      amd64) node_arch="x64" ;; \
      arm64) node_arch="arm64" ;; \
      *) echo "Unsupported Docker target architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${node_arch}.tar.xz" -o /tmp/node.tar.xz; \
    mkdir -p /usr/local/lib/nodejs; \
    tar -xJf /tmp/node.tar.xz -C /usr/local/lib/nodejs --strip-components=1; \
    ln -sf /usr/local/lib/nodejs/bin/node /usr/bin/node; \
    ln -sf /usr/local/lib/nodejs/bin/npm /usr/bin/npm; \
    ln -sf /usr/local/lib/nodejs/bin/npx /usr/bin/npx; \
    test -x /usr/bin/node; \
    /usr/bin/node --version; \
    rm -f /tmp/node.tar.xz

RUN set -eux; \
    curl -fSL "https://github.com/judge0/isolate/archive/ad39cc4d0fbb577fb545910095c9da5ef8fc9a1a.tar.gz" -o /tmp/isolate.tar.gz; \
    mkdir -p /tmp/isolate; \
    tar -xzf /tmp/isolate.tar.gz -C /tmp/isolate --strip-components=1; \
    cd /tmp/isolate; \
    make -j"$(nproc)" install; \
    rm -rf /tmp/isolate /tmp/isolate.tar.gz

RUN set -eux; \
    echo "gem: --no-document" > /root/.gemrc; \
    gem install bundler:2.1.4

WORKDIR /api

RUN set -eux; \
    curl -fSL "https://github.com/judge0/judge0/archive/${JUDGE0_REF}.tar.gz" -o /tmp/judge0.tar.gz; \
    tar -xzf /tmp/judge0.tar.gz -C /api --strip-components=1; \
    rm /tmp/judge0.tar.gz

COPY languages/active.rb /api/db/languages/active.rb
COPY languages/archived.rb /api/db/languages/archived.rb

# The judge0 source tarball ships its own sample judge0.conf at /api/judge0.conf.
# scripts/load-config prefers that path over /judge0.conf and sources it with
# `set -o allexport`, which overwrites anything Compose injected -- so the sample
# defaults (POSTGRES_HOST=db, POSTGRES_DB=judge0) would win and the server would
# never reach the isolated database. The official image avoids this because
# judge0.conf is listed in judge0's .dockerignore; building from the tarball
# keeps it. Overwrite it with ours so load-config reads the isolated settings.
COPY judge0.conf /api/judge0.conf

RUN set -eux; \
    bundle _2.1.4_ config set without "development test"; \
    bundle _2.1.4_ install --jobs "$(nproc)" --retry 3; \
    cat /api/cron/* | crontab -

RUN set -eux; \
    useradd -u 1000 -m -r judge0; \
    echo "judge0 ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/judge0; \
    chmod 0440 /etc/sudoers.d/judge0; \
    mkdir -p /api/tmp /api/log /api/public; \
    chown -R judge0:judge0 /api/tmp /api/log /api/public

EXPOSE 2358

USER judge0

ENTRYPOINT ["/api/docker-entrypoint.sh"]
CMD ["/api/scripts/server"]
