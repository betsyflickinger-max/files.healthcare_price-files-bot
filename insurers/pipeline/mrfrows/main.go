// mrfrows: turn a Transparency in Coverage in-network file into flat price rows for a set of providers.
// Streams the file once, splits the top-level "in_network" array into items, decodes items on worker
// goroutines, keeps rates that point at a provider_reference in -refmap (or list an NPI from -npis inline),
// and writes one gzip CSV row per provider x price. -codes limits billing codes (omit for all codes);
// items for other codes are skipped byte-by-byte without decoding.
package main

import (
	"bufio"
	"bytes"
	"crypto/md5"
	"encoding/hex"
	"encoding/csv"
	"flag"
	"fmt"
	"io"
	"os"
	"regexp"
	"runtime"
	"sort"
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
	// Oct 15, 2026: -layout lines writes one row per price per provider group (TIN) instead of one per NPI, with an
	// npiset id (md5 of the group's sorted in-scope NPIs) and n_npi; -sets gets each distinct NPI list once
	// (npiset,npi rows). Joining the two gives back exactly the flat rows (Aetna repeats prices ~33x per NPI).
	layout := flag.String("layout", "flat", "flat (one row per NPI x price) or lines")
	setsF := flag.String("sets", "", "lines layout: output .csv.gz of npiset,npi")
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
	lines := *layout == "lines"
	hdr := []string{"billing_code_type", "billing_code", "name", "negotiation_arrangement", "npi", "tin", "tin_type",
		"negotiated_type", "negotiated_rate", "billing_class", "setting", "service_code", "billing_code_modifier", "expiration_date",
		"billing_code_type_version", "description", "additional_information", "bundled_codes", "covered_services"}
	var scw *csv.Writer
	var sgz *gzip.Writer
	var sf *os.File
	var sbw *bufio.Writer
	if lines {
		hdr[4] = "npiset"
		hdr = append(hdr, "n_npi")
		if *setsF == "" {
			panic("-layout lines needs -sets")
		}
		sf, err = os.Create(*setsF)
		if err != nil {
			panic(err)
		}
		sgz = gzip.NewWriter(sf)
		sbw = bufio.NewWriterSize(sgz, 8<<20)
		scw = csv.NewWriter(sbw)
		scw.Write([]string{"npiset", "npi"})
	}
	cw.Write(hdr)

	work := make(chan []byte, 4)
	rowsCh := make(chan batchOut, 4)
	var wg sync.WaitGroup
	nw := runtime.NumCPU()
	for i := 0; i < nw; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for b := range work {
				process(b, refs, whos, npis, lines, func(o batchOut) { rowsCh <- o })
			}
		}()
	}
	var nrows, flatRows, nsets int64
	written := map[string]bool{}
	done := make(chan bool)
	go func() {
		for o := range rowsCh {
			for _, st := range o.sets {
				if !written[st.key] {
					written[st.key] = true
					nsets++
					for _, n := range st.npis {
						scw.Write([]string{st.key, n})
					}
				}
			}
			cw.WriteAll(o.rows)
			nrows += int64(len(o.rows))
			flatRows += o.flat
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
	if scw != nil {
		scw.Flush()
		sbw.Flush()
		sgz.Close()
		sf.Close()
	}
	if gz != nil {
		gz.Close()
	}
	sink.Close()
	fmt.Fprintf(os.Stderr, "    done: %d items, %.1f GB uncompressed, %d price rows (%.0f min)\n",
		items, float64(total)/1e9, nrows, time.Since(t0).Minutes())
	if lines {
		fmt.Fprintf(os.Stderr, "    lines layout: %d stored rows stand for %d flat rows; %d distinct NPI lists\n", nrows, flatRows, nsets)
	}
}

type setOut struct {
	key  string
	npis []string
}
type batchOut struct {
	rows [][]string
	sets []setOut
	flat int64
}

func process(b []byte, refs map[string][]uint32, whos []who, npis map[string]bool, lines bool, emitB func(batchOut)) {
	var sets []setOut
	var flat int64
	emit := func(rows [][]string) {
		emitB(batchOut{rows: rows, sets: sets, flat: flat})
		sets, flat = nil, 0
	}
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
		type tk struct{ tin, ttype string }
		var gkeys []tk
		var gsets []setOut
		if lines { // one line per provider group (TIN, TIN type): its in-scope NPIs, sorted, as one list
			byT := map[tk][]string{}
			for _, w := range ws {
				k := tk{w.tin, w.ttype}
				if _, ok := byT[k]; !ok {
					gkeys = append(gkeys, k)
				}
				byT[k] = append(byT[k], w.npi)
			}
			sort.Slice(gkeys, func(i, j int) bool {
				if gkeys[i].tin != gkeys[j].tin {
					return gkeys[i].tin < gkeys[j].tin
				}
				return gkeys[i].ttype < gkeys[j].ttype
			})
			for _, k := range gkeys {
				ns := byT[k]
				sort.Strings(ns)
				h := md5.Sum([]byte(strings.Join(ns, ",")))
				st := setOut{hex.EncodeToString(h[:]), ns}
				gsets = append(gsets, st)
				sets = append(sets, st)
			}
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
			if lines {
				for gi, k := range gkeys {
					st := gsets[gi]
					out = append(out, []string{it.CodeType, string(it.Code), it.Name, it.Arrangement, st.key, k.tin, k.ttype,
						p.Type, rate, p.Class, p.Setting, strings.Join(p.ServiceCode, ","), strings.Join(mods, ","), p.Expiration,
						it.Version, it.Description, p.Additional, bundled, covered, strconv.Itoa(len(st.npis))})
					flat += int64(len(st.npis))
					if len(out) >= 50000 {
						emit(out)
						out = nil
					}
				}
				continue
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
