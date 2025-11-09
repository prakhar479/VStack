FROM golang:1.21-alpine AS builder

WORKDIR /app
COPY storage-node/go.mod storage-node/go.sum ./
RUN go mod download

COPY storage-node/ .
RUN go build -o storage-node main.go

FROM alpine:latest
RUN apk --no-cache add ca-certificates curl
WORKDIR /root/

COPY --from=builder /app/storage-node .

# Create data directory for chunk storage
RUN mkdir -p /data/chunks /data/index

EXPOSE 8081

CMD ["./storage-node"]