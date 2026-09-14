# [Sol] Explicit inputs: no private repository, environment or workstation files.
FROM golang:1.24-alpine AS build
WORKDIR /src
COPY go.mod main.go ./
COPY web ./web
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /demo .
FROM scratch
COPY --from=build /demo /demo
USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["/demo"]
