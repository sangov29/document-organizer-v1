FROM golang:1.24-alpine AS builder

ARG MINIO_VERSION=RELEASE.2025-04-22T22-12-26Z
RUN GOBIN=/out CGO_ENABLED=0 go install "github.com/minio/minio@${MINIO_VERSION}"

FROM alpine:3.21
RUN apk add --no-cache ca-certificates
COPY --from=builder /out/minio /usr/local/bin/minio

EXPOSE 9000 9001
ENTRYPOINT ["minio"]
