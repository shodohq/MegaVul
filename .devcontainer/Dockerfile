FROM ubuntu:24.04

LABEL description="DevContainer for MegaVul"

ENV DEBIAN_FRONTEND=noninteractive

ARG USERNAME=cntuser
ARG USER_UID=10000
ARG USER_GID=10000

# Ubuntu 24.04 has a default 'ubuntu' user at UID 1000, which conflicts with
# updateRemoteUserUID remapping cntuser to the host user's UID (typically 1000)
RUN userdel -r ubuntu 2>/dev/null || true

RUN if ! getent group "${USERNAME}" >/dev/null; then \
  groupadd --gid "${USER_GID}" "${USERNAME}"; \
  fi \
  && if ! id -u "${USERNAME}" >/dev/null 2>&1; then \
  useradd --uid "${USER_UID}" --gid "${USER_GID}" -m "${USERNAME}"; \
  fi


RUN apt-get clean && apt-get update && apt-get install -y locales \
  && locale-gen en_US.UTF-8
ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

RUN apt-get install -y \
  wget curl git vim \
  build-essential cmake pkg-config \
  libicu-dev zlib1g-dev libcurl4-openssl-dev libssl-dev ruby-dev \
  ca-certificates gnupg \
  zip unzip

# nodejs + tree-sitter-cli
RUN curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
RUN echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list
RUN apt-get update && apt-get install -y nodejs
RUN npm install -g tree-sitter-cli

# github-linguist
RUN gem install github-linguist

USER cntuser

# uv (installs to $HOME/.local/bin = /home/cntuser/.local/bin)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH=/home/cntuser/.local/bin:$PATH

# java, scala, sbt via SDKMAN (installs to $HOME/.sdkman = /home/cntuser/.sdkman)
RUN curl -s "https://get.sdkman.io" | bash
RUN bash -c "source /home/cntuser/.sdkman/bin/sdkman-init.sh \
  && sdk install java 17.0.6-amzn \
  && sdk install scala 3.2.2 \
  && sdk install sbt 1.9.9"
ENV PATH=/home/cntuser/.sdkman/candidates/java/current/bin:$PATH
ENV PATH=/home/cntuser/.sdkman/candidates/scala/current/bin:$PATH
ENV PATH=/home/cntuser/.sdkman/candidates/sbt/current/bin:$PATH

# Verify installations
RUN uv --version && npm -v && java --version && scala --version && github-linguist --version && tree-sitter --version
