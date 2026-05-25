# Ansible controller container.
# Runs ansible-core 2.20 + required collections + Docker CLI so it can drive
# the host's Docker engine (mounted via /var/run/docker.sock).
#
# Image stays small by using python:slim and installing only what we need.

FROM python:3.12-slim

ARG ANSIBLE_VERSION=13.7.0
ARG ANSIBLE_CORE_VERSION=2.20.4

# Install Docker CLI (NOT the engine — we use the host's via the mounted socket)
# plus the few system tools the playbooks invoke (nc, curl, git, tar, gzip).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        netcat-openbsd \
        openssh-client \
        git \
        tar \
        gzip \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
       | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
       https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

# Install Ansible and required Python libs at pinned versions
RUN pip install --no-cache-dir \
        "ansible-core==${ANSIBLE_CORE_VERSION}" \
        "ansible==${ANSIBLE_VERSION}" \
        "ansible-lint" \
        "requests" \
        "docker" \
        "jmespath"

# Install collections used by the playbooks
RUN ansible-galaxy collection install \
        community.docker:>=4.3.0 \
        community.general:>=10.5.0 \
        ansible.posix:>=2.0.0

WORKDIR /workspace

# Default to an interactive shell — users will run ansible-playbook commands
# inside the container, or `docker compose run --rm controller ansible-playbook ...`
CMD ["bash"]
