FROM node:22-alpine AS build

WORKDIR /app
RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN for attempt in 1 2 3; do \
      pnpm install --frozen-lockfile && break; \
      if [ "$attempt" = 3 ]; then exit 1; fi; \
      echo "Dependency download failed; retrying ($attempt/3)..."; \
      sleep 5; \
    done

COPY . .
# URL được truyền vào qua --build-arg khi chạy docker build
# (hoặc thông qua script build_and_push_ghcr.ps1/.sh đọc từ .env.deploy)
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_AGENT_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NEXT_PUBLIC_AGENT_BASE_URL=${NEXT_PUBLIC_AGENT_BASE_URL}
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build



EXPOSE 3000
CMD ["pnpm", "start"]
