# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
# Project Desk in a container. Mount the project at /repo, run as your own user so saved files keep
# your ownership, and publish the port on the host's loopback only:
#   docker run --rm -p 127.0.0.1:4700:4700 --user "$(id -u):$(id -g)" -v "$PWD:/repo" project-desk:local
# Inside the container the desk listens on every address. It answers only requests whose Host header is
# localhost/127.0.0.1/[::1] with its own port, so keep the host and container ports equal. That check
# stops browsers, not other machines: never publish the port beyond 127.0.0.1.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /src
COPY pyproject.toml uv.lock README.md LICENSE.md ./
COPY src ./src
RUN uv pip install --system --no-cache . && rm -rf /src

WORKDIR /repo
EXPOSE 4700
HEALTHCHECK --interval=15s --timeout=5s CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('DESK_PORT', '4700') + '/', timeout=3)"
ENTRYPOINT ["desk"]
CMD ["serve", "--host", "0.0.0.0", "--port", "4700"]
