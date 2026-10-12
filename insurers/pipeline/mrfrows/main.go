// mrfrows: turn a Transparency in Coverage in-network file into flat price rows for a set of providers.
// Streams the file once, splits the top-level "in_network" array into items, decodes items on worker
// goroutines, keeps rates that point at a provider_reference in -refmap (or list an NPI from -npis inline),
// and writes the prices out (see sink.go): flat CSV (-out - or x.csv.gz, the original output), flat Parquet
// (-out x.parquet -format flat), or each price once per provider group with its NPI list stored separately
// (-out x.parquet -format lines -npisets y.parquet). -codes limits billing codes (omit for all codes);
// items for other codes are skipped byte-by-byte without decoding.
package main

import (
	"bufio"
	"bytes"
	"crypto/sha256"
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
	outF := flag.String("out", "", "output: - (CSV on stdout), x.csv.gz, or x.parquet")
	format := flag.String("format", "flat", "Parquet layout: flat or lines")
	setsF := flag.String("npisets", "", "with -format lines: where to write the NPI lists")
	var kv multiFlag
	flag.Var(&kv, "const", "column=value written on every Parquet row (repeatable)")
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

	out := newSink(*outF, *format, *setsF, kv)

	work := make(chan []byte, 4)
	rowsCh := make(chan []line, 4)
	var wg sync.WaitGroup
	nw := runtime.NumCPU()
	for i := 0; i < nw; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for b := range work {
				process(b, refs, whos, npis, func(o []line) { rowsCh <- o })
			}
		}()
	}
	var nrows int64 // flat rows written so far (read by the progress line only)
	done := make(chan bool)
	go func() {
		for ls := range rowsCh {
			out.write(ls)
			nrows, _, _ = out.counts()
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
	out.close()
	flat, stored, sets := out.counts()
	fmt.Fprintf(os.Stderr, "    done: %d items, %.1f GB uncompressed, %d price rows (%.0f min)\n",
		items, float64(total)/1e9, flat, time.Since(t0).Minutes())
	if stored != flat {
		fmt.Fprintf(os.Stderr, "    stored as %d lines + %d NPI lists (%.1fx fewer rows)\n", stored, sets, float64(flat)/float64(max(stored, 1)))
	}
}

type multiFlag []string

func (m *multiFlag) String() string     { return strings.Join(*m, ",") }
func (m *multiFlag) Set(v string) error { *m = append(*m, v); return nil }

// process turns one in_network item into lines: for each negotiated_rates entry, its in-scope providers are
// grouped by (TIN, TIN type) with the NPIs sorted, and each negotiated price becomes one line per group.
// Expanding every line by its NPIs gives exactly the rows the original flat output had.
func process(b []byte, refs map[string][]uint32, whos []who, npis map[string]bool, emit func([]line)) {
	var it item
	if err := json.Unmarshal(b, &it); err != nil {
		fmt.Fprintln(os.Stderr, "    ! decode error:", err)
		return
	}
	var out []line
	var flat int
	for _, nr := range it.Rates {
		seen := map[who]bool{}
		type grp struct {
			tin, ttype string
			npis       []string
		}
		var gs []*grp
		gi := map[[2]string]*grp{}
		add := func(w who) {
			if seen[w] {
				return
			}
			seen[w] = true
			k := [2]string{w.tin, w.ttype}
			g := gi[k]
			if g == nil {
				g = &grp{tin: w.tin, ttype: w.ttype}
				gi[k] = g
				gs = append(gs, g)
			}
			g.npis = append(g.npis, w.npi)
		}
		for _, ref := range nr.Refs {
			for _, wi := range refs[string(ref)] {
				add(whos[wi])
			}
		}
		for _, g := range nr.Groups {
			for _, n := range g.NPI {
				if npis[string(n)] {
					add(who{string(n), strings.ReplaceAll(string(g.TIN.Value), "-", ""), g.TIN.Type})
				}
			}
		}
		if len(gs) == 0 {
			continue
		}
		sets := make([]*npiSet, len(gs))
		for i, g := range gs {
			sort.Strings(g.npis)
			h := sha256.New()
			for _, n := range g.npis {
				h.Write([]byte(n))
				h.Write([]byte{0})
			}
			s := &npiSet{npis: g.npis}
			copy(s.key[:], h.Sum(nil))
			sets[i] = s
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
			svc, mod := strings.Join(p.ServiceCode, ","), strings.Join(mods, ",")
			for i, g := range gs {
				out = append(out, line{it.CodeType, string(it.Code), it.Name, it.Arrangement, g.tin, g.ttype,
					p.Type, rate, p.Class, p.Setting, svc, mod, p.Expiration, sets[i]})
				flat += len(g.npis)
				if len(out) >= 20000 || flat >= 200000 {
					emit(out)
					out, flat = nil, 0
				}
			}
		}
	}
	if len(out) > 0 {
		emit(out)
	}
}
