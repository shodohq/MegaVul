FROM ubuntu:22.04

LABEL description="DevContainer for MegaVul"

ENV DEBIAN_FRONTEND=noninteractive

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
RUN npm install -g tree-sitter-cli@0.20.7

# github-linguist
RUN gem install github-linguist

# uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH=/root/.local/bin:$PATH

# java, scala, sbt via SDKMAN
RUN curl -s "https://get.sdkman.io" | bash
RUN bash -c "source /root/.sdkman/bin/sdkman-init.sh \
    && sdk install java 17.0.6-amzn \
    && sdk install scala 3.2.2 \
    && sdk install sbt 1.9.9"
ENV PATH=/root/.sdkman/candidates/java/current/bin:$PATH
ENV PATH=/root/.sdkman/candidates/scala/current/bin:$PATH
ENV PATH=/root/.sdkman/candidates/sbt/current/bin:$PATH

# Verify installations
RUN uv --version && npm -v && java --version && scala --version && github-linguist --version && tree-sitter --version
