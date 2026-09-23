FROM golang:1.26-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY *.go ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /market .
FROM scratch
COPY --from=build /market /market
USER 10002:10002
EXPOSE 8090
HEALTHCHECK --interval=10s --timeout=4s CMD ["/market", "health"]
ENTRYPOINT ["/market"]
