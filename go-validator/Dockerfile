# =============================================================================
# Go Validator — Multi-stage build (small final image)
# =============================================================================
FROM golang:1.23-alpine AS builder
WORKDIR /app

# Cache dependencies layer
COPY go.mod go.sum ./
RUN go mod download

# Build the binary
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o validator .

# ── Runtime stage ────────────────────────────────────────────────────────────
FROM alpine:3.20
RUN apk add --no-cache ca-certificates wget
WORKDIR /app
COPY --from=builder /app/validator /app/validator
EXPOSE 8080
ENTRYPOINT ["/app/validator"]
