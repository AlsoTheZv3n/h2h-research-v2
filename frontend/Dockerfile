# syntax=docker/dockerfile:1

# ---------- build ----------
FROM node:22-alpine AS builder

WORKDIR /app

RUN corepack enable

# Manifests first: this layer only busts when dependencies change, so editing a
# component does not reinstall node_modules. package.json pins the pnpm version via
# `packageManager`, so corepack installs the one that wrote the lockfile rather than
# whatever is newest today.
COPY package.json pnpm-lock.yaml ./

# minimumReleaseAge is pnpm's supply-chain guard: it refuses packages published in
# the last few days, so a freshly-compromised release cannot be pulled in before
# anyone notices. It earns its keep at `pnpm add` time, on a developer's machine.
# Here it only blocks installing versions that were already resolved, reviewed and
# committed, each pinned by integrity hash -- nothing left to guard, and with it on
# the image cannot build the lockfile it was handed. Written to .npmrc rather than
# passed as a flag because `pnpm build` re-verifies deps and would hit the guard
# again on its own install.
RUN printf 'minimum-release-age=0\n' > .npmrc \
    && pnpm install --frozen-lockfile

COPY . .

# Same-origin /api: nginx below proxies it to the api service, so the browser needs
# no CORS and no build-time knowledge of where the backend lives.
ENV VITE_API_BASE_URL=/api
RUN pnpm build

# ---------- runtime ----------
# nginx-unprivileged: runs as uid 101 out of the box. The stock nginx image needs
# root to bind :80 and drop privileges, which is more than serving static files
# should ever ask for.
FROM nginxinc/nginx-unprivileged:alpine AS runtime

COPY --chown=nginx:nginx nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder --chown=nginx:nginx /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["sh", "-c", "wget -qO- http://localhost:8080/ >/dev/null || exit 1"]
