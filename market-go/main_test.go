package main

import (
	"net/http/httptest"
	"testing"
)

func TestParse(t *testing.T) {
	for _, q := range []string{"source=modern&symbol=NQ&after=NaN&limit=10", "source=modern&symbol=NQ&after=+Inf&limit=10", "source=live&symbol=NQ&after=1&limit=10", "source=modern&symbol=NQ&after=1&limit=200001", "source=modern&symbol=OTHER&after=1&limit=10"} {
		if _, e := parse(httptest.NewRequest("GET", "/ticks?"+q, nil)); e == nil {
			t.Fatalf("accepted %s", q)
		}
	}
	if _, e := parse(httptest.NewRequest("GET", "/ticks?source=modern&symbol=NQ&after=1&limit=10", nil)); e != nil {
		t.Fatal(e)
	}
}
