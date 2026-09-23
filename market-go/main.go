// Historical tick service. It has no broker client or live mode.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/jackc/pgx/v5/pgxpool"
	"log"
	"math"
	"net/http"
	"os"
	"strconv"
	"time"
)

type request struct {
	source, symbol string
	after          float64
	limit          int
}

func parse(r *http.Request) (request, error) {
	q := r.URL.Query()
	v := request{source: q.Get("source"), symbol: q.Get("symbol")}
	if v.source != "legacy" && v.source != "modern" {
		return v, fmt.Errorf("invalid source")
	}
	switch v.symbol {
	case "ES", "MES", "NQ", "MNQ", "YM", "MYM", "GC", "MGC":
	default:
		return v, fmt.Errorf("invalid symbol")
	}
	var err error
	v.after, err = strconv.ParseFloat(q.Get("after"), 64)
	if err != nil || math.IsNaN(v.after) || math.IsInf(v.after, 0) || v.after < 0 {
		return v, fmt.Errorf("invalid cursor")
	}
	v.limit, err = strconv.Atoi(q.Get("limit"))
	if err != nil || v.limit < 1 || v.limit > 200000 {
		return v, fmt.Errorf("invalid limit")
	}
	return v, nil
}
func ticks(db *pgxpool.Pool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		v, err := parse(r)
		if err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 25*time.Second)
		defer cancel()
		// WITH TIES includes all ticks at the final timestamp, avoiding lost prints.
		sql := fmt.Sprintf("SELECT t,id,timestamp,price,volume,side FROM %s.tape_trades WHERE symbol=$1 AND t>$2 ORDER BY t FETCH FIRST $3 ROWS WITH TIES", v.source)
		rows, err := db.Query(ctx, sql, v.symbol, v.after, v.limit)
		if err != nil {
			log.Print("tick query failed")
			http.Error(w, "market unavailable", 503)
			return
		}
		defer rows.Close()
		out := make([][]any, 0, v.limit)
		for rows.Next() {
			var t, p, vol float64
			var id, stamp, side string
			if err = rows.Scan(&t, &id, &stamp, &p, &vol, &side); err != nil {
				http.Error(w, "invalid market data", 503)
				return
			}
			out = append(out, []any{t, id, stamp, p, vol, side})
		}
		if rows.Err() != nil {
			http.Error(w, "market unavailable", 503)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(out)
	}
}
func main() {
	if len(os.Args) > 1 && os.Args[1] == "health" {
		c := http.Client{Timeout: 3 * time.Second}
		r, e := c.Get("http://127.0.0.1:8090/health")
		if e != nil || r.StatusCode != 200 {
			os.Exit(1)
		}
		r.Body.Close()
		return
	}
	cfg, err := pgxpool.ParseConfig(os.Getenv("MARKET_DSN"))
	if err != nil {
		log.Fatal("invalid database configuration")
	}
	cfg.MaxConns = 8
	db, err := pgxpool.NewWithConfig(context.Background(), cfg)
	if err != nil {
		log.Fatal("database initialization failed")
	}
	defer db.Close()
	mux := http.NewServeMux()
	mux.HandleFunc("GET /ticks", ticks(db))
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()
		if db.Ping(ctx) != nil {
			http.Error(w, "unavailable", 503)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"status":"ok","mode":"historical","language":"Go"}`))
	})
	server := http.Server{Addr: ":8090", Handler: mux, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second, WriteTimeout: 30 * time.Second, IdleTimeout: 30 * time.Second}
	log.Fatal(server.ListenAndServe())
}
