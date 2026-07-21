FROM ubuntu:22.04
LABEL maintainer="ProxxBot" \
      description="Columbia Group Agent System — task agent" \
      version="1.0"

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    NODE_VERSION=22

# Base tools
RUN apt-get update -qq && apt-get install -y -qq \
    curl ca-certificates git python3 python3-pip \
    postgresql-client locales tzdata \
    && locale-gen en_US.UTF-8 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# OpenClaw
RUN npm install -g openclaw

# Python deps for decision logging
RUN pip3 install psycopg2-binary requests --quiet

# Workspace
RUN mkdir -p /root/clawd/memory /root/clawd/skills
WORKDIR /root/clawd

# Agent bootstrap files
COPY agents.md         /root/clawd/AGENTS.md
COPY soul_placeholder.md  /root/clawd/SOUL.md
COPY identity_placeholder.md /root/clawd/IDENTITY.md
COPY heartbeat.md      /root/clawd/HEARTBEAT.md
COPY user.md           /root/clawd/USER.md
COPY memory.md         /root/clawd/MEMORY.md
COPY decision_logger.py /root/clawd/decision_logger.py
COPY entrypoint.sh     /entrypoint.sh

RUN chmod +x /entrypoint.sh

# OpenClaw gateway port
EXPOSE 18789

ENTRYPOINT ["/entrypoint.sh"]
