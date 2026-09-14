// [Sol] Verify that a showcase cannot expose trading routes or arbitrary files.
package main

import (
	"net/http/httptest"
	"strings"
	"testing"
)

func TestPublicSurface(t *testing.T) {
	for _, path := range []string{"/api/orders", "/api/topstep/accounts", "/.env", "/main.go", "/web/", "/../main.go"} {
		w := httptest.NewRecorder()
		handler().ServeHTTP(w, httptest.NewRequest("GET", path, nil))
		if w.Code != 404 {
			t.Errorf("%s: got %d", path, w.Code)
		}
	}
	w := httptest.NewRecorder()
	handler().ServeHTTP(w, httptest.NewRequest("POST", "/", nil))
	if w.Code != 405 {
		t.Fatal(w.Code)
	}
	w = httptest.NewRecorder()
	handler().ServeHTTP(w, httptest.NewRequest("GET", "/", nil))
	if w.Code != 200 || !strings.Contains(w.Header().Get("Content-Security-Policy"), "connect-src 'none'") {
		t.Fatal("missing page or network restriction")
	}
}
