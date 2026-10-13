// mrfrows: turn a Transparency in Coverage in-network file into flat price rows for a set of providers.
// Streams the file once, splits the top-level "in_network" array into items, decodes items on worker
// goroutines, keeps rates that point at a provider_reference in -refmap (or list an NPI from -npis inline),
// and writes one gzip CSV row per provider x price. -codes limits billing codes (omit for all codes);
// items for other codes are skipped byte-by-byte without decoding.
package main

import (
	"bufio"
	"bytes"
	"encoding/csv"
	"flag"
	"fmt"
	"io"
	"os"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"

	json "github.com/goccy/go-json"
	gzip "github.com/klauspost/compress/gzip"
)

type flexStr string

func (f *flexStr) UnmarshalJSON(b []byte) error {
	*f = flexStr(strings.Trim(string(b), `"`))
	return nil
}

type tin struct {
	Type  string  `json:"type"`
	Value flexStr `json:"value"`
}
type group struct {
	NPI []flexStr `json:"npi"`
	TIN tin       `json:"tin"`
}
type price struct {
	Type        string    `json:"negotiated_type"`
	Rate        flexStr   `json:"negotiated_rate"`
	Expiration  string    `json:"expiration_date"`
	ServiceCode []string  `json:"service_code"`
	Class       string    `json:"billing_class"`
	Setting     string    `json:"setting"`
	Modifier    []flexStr `json:"billing_code_modifier"`
	Additional  string    `json:"additional_information"`
}
type rate struct {
	Refs   []flexStr `json:"provider_references"`
	Groups []group   `json:"provider_groups"`
	Prices []price   `json:"negotiated_prices"`
}
type item struct {
	Arrangement string  `json:"negotiation_arrangement"`
	Name        string  `json:"name"`
	CodeType    string  `json:"billing_code_type"`
	Code        flexStr `json:"billing_code"`
	Rates       []rate  `json:"negotiated_rates"`
	// Kept since Oct 13, 2026 (appended columns; nothing downstream depends on them yet)
	Version     string          `json:"billing_code_type_version"`
	Description string          `json:"description"`
	Bundled     json.RawMessage `json:"bundled_codes"`
	Covered     json.RawMessage `json:"covered_services"`
}

// compactJSON turns a raw JSON value (array/object) into one short line; null or missing -> "".
func compactJSON(r json.RawMessage) string {
	t := bytes.TrimSpace(r)
	if len(t) == 0 || string(t) == "null" || string(t) == "[]" {
		return ""
	}
	var b bytes.Buffer
	if err := json.Compact(&b, t); err != nil {
		return string(t)
	}
	return b.String()
}

type who struct{ npi, tin, ttype string }

var codeRe = regexp.MustCompile(`"billing_code"\s*:\s*"?([^",}\s]+)`)

// eachLine streams a text file line by line (never holds the whole file in memory).
func eachLine(p string, fn func(string)) {
	if p == "" {
		return
	}
	f, err := os.Open(p)
	if err != nil {
		panic(err)
	}
	defer f.Close()
	sc := bufio.NewScanner(bufio.NewReaderSize(f, 8<<20))
	sc.Buffer(make([]byte, 1<<20), 64<<20)
	for sc.Scan() {
		if l := strings.TrimSpace(sc.Text()); l != "" {
			fn(l)
		}
	}
	if err := sc.Err(); err != nil {
		panic(err)
	}
}

func main() {
	in := flag.String("in", "", "input .json.gz or .json")
	refF := flag.String("refmap", "", "TSV: provider_group_id, npi, tin, tin_type")
	npiF := flag.String("npis", "", "NPIs to keep when listed inline")
	codeF := flag.String("codes", "", "billing codes to keep (omit = all)")
	outF := flag.String("out", "", "output .csv.gz")
	flag.Parse()

	// Provider references: each distinct (npi, tin, tin_type) is stored once and referenced by index,
	// so a statewide roster (hundreds of millions of group x provider pairs) fits in memory.
	refs := map[string][]uint32{}
	whoIdx := map[who]uint32{}
	var whos []who
	eachLine(*refF, func(l string) {
		p := strings.Split(l, "\t")
		if len(p) < 4 {
			return
		}
		w := who{p[1], p[2], p[3]}
		i, ok := whoIdx[w]
		if !ok {
			i = uint32(len(whos))
			w = who{strings.Clone(p[1]), strings.Clone(p[2]), strings.Clone(p[3])}
			whoIdx[w] = i
			whos = append(whos, w)
		}
		r, ok := refs[p[0]]
		if !ok {
			r = make([]uint32, 0, 4)
			refs[strings.Clone(p[0])] = r
		}
		refs[p[0]] = append(r, i)
	})
	whoIdx = nil
	runtime.GC()
	fmt.Fprintf(os.Stderr, "    refmap: %d groups, %d distinct providers\n", len(refs), len(whos))
	npis := map[string]bool{}
	eachLine(*npiF, func(n string) { npis[n] = true })
	var codes map[string]bool
	if *codeF != "" {
		codes = map[string]bool{}
		eachLine(*codeF, func(c string) { codes[c] = true })
	}

	f, err := os.Open(*in)
	if err != nil {
		panic(err)
	}
	var r io.Reader = f
	if strings.HasSuffix(*in, ".gz") {
		g, err := gzip.NewReader(bufio.NewReaderSize(f, 8<<20))
		if err != nil {
			panic(err)
		}
		r = g
	}
	br := bufio.NewReaderSize(r, 32<<20)

	var sink io.WriteCloser
	var gz *gzip.Writer
	if *outF == "-" { // plain CSV on stdout, for streaming straight into Parquet
		sink = os.Stdout
	} else {
		of, err := os.Create(*outF)
		if err != nil {
			panic(err)
		}
		gz = gzip.NewWriter(of)
		sink = of
	}
	var w io.Writer = sink
	if gz != nil {
		w = gz
	}
	bw := bufio.NewWriterSize(w, 8<<20)
	cw := csv.NewWriter(bw)
	cw.Write([]string{"billing_code_type", "billing_code", "name", "negotiation_arrangement", "npi", "tin", "tin_type",
		"negotiated_type", "negotiated_rate", "billing_class", "setting", "service_code", "billing_code_modifier", "expiration_date",
		"billing_code_type_version", "description", "additional_information", "bundled_codes", "covered_services"})

	work := make(chan []byte, 4)
	rowsCh := make(chan [][]string, 4)
	var wg sync.WaitGroup
	nw := runtime.NumCPU()
	for i := 0; i < nw; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for b := range work {
				process(b, refs, whos, npis, func(o [][]string) { rowsCh <- o })
			}
		}()
	}
	var nrows int64
	done := make(chan bool)
	go func() {
		for rs := range rowsCh {
			cw.WriteAll(rs)
			nrows += int64(len(rs))
		}
		done <- true
	}()

	depth := 0
	inStr, esc, capKey, inArr := false, false, false, false
	var key bytes.Buffer
	lastKey := ""
	var buf bytes.Buffer
	mode := 0 // 0 none, 1 deciding, 2 keep, 3 skip
	var total, items int64
	t0 := time.Now()
	for {
		c, err := br.ReadByte()
		if err != nil {
			break
		}
		total++
		if mode == 1 || mode == 2 {
			buf.WriteByte(c)
		}
		if inStr {
			if esc {
				esc = false
			} else if c == '\\' {
				esc = true
			} else if c == '"' {
				inStr = false
				if capKey {
					lastKey = key.String()
					capKey = false
				}
			} else if capKey {
				key.WriteByte(c)
			}
			continue
		}
		switch c {
		case '"':
			inStr = true
			if depth == 1 {
				key.Reset()
				capKey = true
			}
		case '{', '[':
			depth++
			if depth == 2 && c == '[' && lastKey == "in_network" {
				inArr = true
			} else if inArr && depth == 3 && c == '{' {
				buf.Reset()
				buf.WriteByte('{')
				if codes == nil {
					mode = 2
				} else {
					mode = 1
				}
			}
		case '}', ']':
			depth--
			if inArr && depth == 2 && c == '}' {
				items++
				keep := mode == 2
				if mode == 1 {
					m := codeRe.FindSubmatch(buf.Bytes())
					keep = m != nil && codes[string(m[1])]
				}
				if keep {
					b := make([]byte, buf.Len())
					copy(b, buf.Bytes())
					work <- b
				}
				mode = 0
				if items%100000 == 0 {
					fmt.Fprintf(os.Stderr, "    ... %d items, %.1f GB uncompressed, %d rows (%.0f min)\n",
						items, float64(total)/1e9, nrows, time.Since(t0).Minutes())
				}
			} else if inArr && depth == 1 && c == ']' {
				inArr = false
			}
		}
		if mode == 1 && (buf.Len() == 512 || buf.Len()%8192 == 0) {
			if m := codeRe.FindSubmatch(buf.Bytes()); m != nil {
				if codes[string(m[1])] {
					mode = 2
				} else {
					mode = 3
					buf.Reset()
				}
			} else if buf.Len() > 1<<20 {
				mode = 2
			}
		}
	}
	close(work)
	wg.Wait()
	close(rowsCh)
	<-done
	cw.Flush()
	bw.Flush()
	if gz != nil {
		gz.Close()
	}
	sink.Close()
	fmt.Fprintf(os.Stderr, "    done: %d items, %.1f GB uncompressed, %d price rows (%.0f min)\n",
		items, float64(total)/1e9, nrows, time.Since(t0).Minutes())
}

func process(b []byte, refs map[string][]uint32, whos []who, npis map[string]bool, emit func([][]string)) {
	var it item
	if err := json.Unmarshal(b, &it); err != nil {
		fmt.Fprintln(os.Stderr, "    ! decode error:", err)
		return
	}
	var out [][]string
	bundled, covered := compactJSON(it.Bundled), compactJSON(it.Covered)
	for _, nr := range it.Rates {
		seen := map[who]bool{}
		var ws []who
		for _, ref := range nr.Refs {
			for _, wi := range refs[string(ref)] {
				w := whos[wi]
				if !seen[w] {
					seen[w] = true
					ws = append(ws, w)
				}
			}
		}
		for _, g := range nr.Groups {
			for _, n := range g.NPI {
				if npis[string(n)] {
					w := who{string(n), strings.ReplaceAll(string(g.TIN.Value), "-", ""), g.TIN.Type}
					if !seen[w] {
						seen[w] = true
						ws = append(ws, w)
					}
				}
			}
		}
		if len(ws) == 0 {
			continue
		}
		for _, p := range nr.Prices {
			mods := make([]string, len(p.Modifier))
			for i, m := range p.Modifier {
				mods[i] = string(m)
			}
			rate := string(p.Rate)
			if v, err := strconv.ParseFloat(rate, 64); err == nil {
				rate = strconv.FormatFloat(v, 'f', -1, 64)
			}
			for _, w := range ws {
				out = append(out, []string{it.CodeType, string(it.Code), it.Name, it.Arrangement, w.npi, w.tin, w.ttype,
					p.Type, rate, p.Class, p.Setting, strings.Join(p.ServiceCode, ","), strings.Join(mods, ","), p.Expiration,
					it.Version, it.Description, p.Additional, bundled, covered})
				if len(out) >= 50000 {
					emit(out)
					out = nil
				}
			}
		}
	}
	if len(out) > 0 {
		emit(out)
	}
}
