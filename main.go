// [Sol] Standalone portfolio demo. No broker, credentials, or private engine.
package main

import (
	"embed"
	"io/fs"
	"log"
	"net/http"
	"time"
)

//go:embed web/*
var assets embed.FS

func handler() http.Handler {
	files, err := fs.Sub(assets, "web")
	if err != nil {
		panic(err)
	}
	allowed := map[string]bool{"/": true, "/app.js": true, "/style.css": true}
	static := http.FileServer(http.FS(files))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'none'; font-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "no-referrer")
		w.Header().Set("Cache-Control", "no-store")
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			w.Header().Set("Allow", "GET, HEAD")
			http.Error(w, "Method not allowed", 405)
			return
		}
		if r.URL.Path == "/healthz" {
			w.Write([]byte("ok\n"))
			return
		}
		if !allowed[r.URL.Path] {
			http.NotFound(w, r)
			return
		}
		static.ServeHTTP(w, r)
	})
}
func main() {
	server := &http.Server{Addr: ":8080", Handler: handler(), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second, WriteTimeout: 15 * time.Second, IdleTimeout: 60 * time.Second, MaxHeaderBytes: 16 << 10}
	log.Print("[Sol] PurpleChart portfolio demo on :8080 — synthetic data only")
	log.Fatal(server.ListenAndServe())
}
