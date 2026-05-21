// =============================================================================
// FreshMart Go Validator — Schema-validates events arriving from NiFi
// Endpoint: POST /validate  → returns 200 OK or 400 with error details
// Endpoint: GET  /health    → readiness probe
// =============================================================================
package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	_ "github.com/lib/pq"
)

// SaleEvent — schema for POS sale messages from NiFi
type SaleEvent struct {
	StoreID    string  `json:"store_id"`
	SKU        string  `json:"sku"`
	Qty        int     `json:"qty"`
	UnitPrice  float64 `json:"unit_price"`
	EmpID      string  `json:"emp_id"`
	SaleTs     string  `json:"sale_ts"`
}

type ValidationResult struct {
	Valid  bool     `json:"valid"`
	Errors []string `json:"errors,omitempty"`
}

var db *sql.DB

func main() {
	connStr := fmt.Sprintf(
		"host=%s port=%s user=%s password=%s dbname=%s sslmode=disable",
		os.Getenv("DB_HOST"), os.Getenv("DB_PORT"),
		os.Getenv("DB_USER"), os.Getenv("DB_PASS"),
		os.Getenv("DB_NAME"),
	)

	var err error
	for i := 0; i < 30; i++ {
		db, err = sql.Open("postgres", connStr)
		if err == nil {
			if perr := db.Ping(); perr == nil {
				break
			}
		}
		log.Printf("DB not ready, retry %d...", i+1)
		time.Sleep(2 * time.Second)
	}
	if err != nil {
		log.Fatalf("DB connect failed: %v", err)
	}
	defer db.Close()
	log.Println("✓ Connected to PostgreSQL")

	http.HandleFunc("/health",   healthHandler)
	http.HandleFunc("/validate", validateHandler)
	http.HandleFunc("/metrics",  metricsHandler)

	log.Println("→ Go validator listening on :8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}

// healthHandler — readiness probe used by docker-compose healthcheck.
func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	if err := db.Ping(); err != nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"status": "down", "db": err.Error()})
		return
	}
	json.NewEncoder(w).Encode(map[string]string{"status": "up", "db": "connected"})
}

// validateHandler — NiFi InvokeHTTP POSTs sale JSON; we respond with verdict.
func validateHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}

	var ev SaleEvent
	if err := json.NewDecoder(r.Body).Decode(&ev); err != nil {
		respond(w, ValidationResult{Valid: false, Errors: []string{"malformed json: " + err.Error()}}, 400)
		return
	}

	var errs []string
	if ev.StoreID == ""              { errs = append(errs, "store_id required") }
	if ev.SKU == ""                  { errs = append(errs, "sku required") }
	if ev.Qty <= 0                   { errs = append(errs, "qty must be > 0") }
	if ev.UnitPrice <= 0             { errs = append(errs, "unit_price must be > 0") }
	if ev.SaleTs == ""               { errs = append(errs, "sale_ts required") }
	if _, err := time.Parse(time.RFC3339, ev.SaleTs); err != nil && ev.SaleTs != "" {
		errs = append(errs, "sale_ts must be ISO8601")
	}

	// Cross-reference SKU against product catalog
	if ev.SKU != "" {
		var exists bool
		_ = db.QueryRow("SELECT EXISTS(SELECT 1 FROM PRODUCT_CATALOG WHERE sku=$1)", ev.SKU).Scan(&exists)
		if !exists {
			errs = append(errs, "unknown sku: "+ev.SKU)
		}
	}

	if len(errs) > 0 {
		respond(w, ValidationResult{Valid: false, Errors: errs}, 400)
		return
	}
	respond(w, ValidationResult{Valid: true}, 200)
}

// metricsHandler — reports validation counts for the dashboard.
func metricsHandler(w http.ResponseWriter, r *http.Request) {
	var saleCount, feedbackCount, reorderCount int
	_ = db.QueryRow("SELECT COUNT(*) FROM DW_SALES_FACT").Scan(&saleCount)
	_ = db.QueryRow("SELECT COUNT(*) FROM CUSTOMER_FEEDBACK").Scan(&feedbackCount)
	_ = db.QueryRow("SELECT COUNT(*) FROM REORDER_LOG").Scan(&reorderCount)

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	json.NewEncoder(w).Encode(map[string]int{
		"sales":    saleCount,
		"feedback": feedbackCount,
		"reorders": reorderCount,
	})
}

func respond(w http.ResponseWriter, body interface{}, code int) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(body)
}
