package main

// Output writers. The reader produces "lines": one negotiated price for one provider group (a TIN) with the
// sorted list of in-scope NPIs it applies to. Each sink turns lines into one of three outputs:
//   csv   the original flat CSV (one row per NPI x price), kept for old callers (-out - or -out x.csv.gz)
//   flat  the same flat rows written straight to Parquet (-out x.parquet -format flat)
//   lines one row per line plus an npiset number, and a second file listing each distinct NPI list once
//         (-out x.parquet -format lines -npisets y.parquet). Joining the two gives back exactly the flat rows.

import (
	"bufio"
	"encoding/csv"
	"fmt"
	"io"
	"os"
	"strings"

	gzip "github.com/klauspost/compress/gzip"
	"github.com/parquet-go/parquet-go"
	"github.com/parquet-go/parquet-go/compress/zstd"
)

type npiSet struct {
	npis []string
	key  [16]byte
}

type line struct {
	codeType, code, name, arr, tin, ttype, ntype, rate, class, setting, svc, mods, exp string
	set                                                                                *npiSet
}

type sink interface {
	write([]line)
	close() // finish the output (or remove it when nothing was written)
	counts() (flatRows, storedRows, sets int64)
}

var flatHeader = []string{"billing_code_type", "billing_code", "name", "negotiation_arrangement", "npi", "tin", "tin_type",
	"negotiated_type", "negotiated_rate", "billing_class", "setting", "service_code", "billing_code_modifier", "expiration_date"}

// ---------- csv (original output) ----------

type csvSink struct {
	f     *os.File
	gz    *gzip.Writer
	bw    *bufio.Writer
	cw    *csv.Writer
	nrows int64
}

func newCSVSink(out string) *csvSink {
	s := &csvSink{}
	var w io.Writer
	if out == "-" { // plain CSV on stdout
		s.f = os.Stdout
		w = os.Stdout
	} else {
		f, err := os.Create(out)
		if err != nil {
			panic(err)
		}
		s.f, s.gz = f, gzip.NewWriter(f)
		w = s.gz
	}
	s.bw = bufio.NewWriterSize(w, 8<<20)
	s.cw = csv.NewWriter(s.bw)
	s.cw.Write(flatHeader)
	return s
}

func (s *csvSink) write(ls []line) {
	for i := range ls {
		l := &ls[i]
		for _, n := range l.set.npis {
			s.cw.Write([]string{l.codeType, l.code, l.name, l.arr, n, l.tin, l.ttype, l.ntype, l.rate, l.class, l.setting, l.svc, l.mods, l.exp})
			s.nrows++
		}
	}
}

func (s *csvSink) close() {
	s.cw.Flush()
	s.bw.Flush()
	if s.gz != nil {
		s.gz.Close()
	}
	s.f.Close()
}

func (s *csvSink) counts() (int64, int64, int64) { return s.nrows, s.nrows, 0 }

// ---------- Parquet ----------

// Columns in the same order as the old Python-written tables. "dict" = dictionary-encoded (few distinct values).
type flatRow struct {
	ReportingEntityName    string `parquet:"reporting_entity_name,dict"`
	FileLabel              string `parquet:"file_label,dict"`
	LastUpdatedOn          string `parquet:"last_updated_on,dict"`
	BillingCodeType        string `parquet:"billing_code_type,dict"`
	BillingCode            string `parquet:"billing_code,dict"`
	Name                   string `parquet:"name,dict"`
	NegotiationArrangement string `parquet:"negotiation_arrangement,dict"`
	NPI                    string `parquet:"npi"`
	TIN                    string `parquet:"tin"`
	TINType                string `parquet:"tin_type,dict"`
	NegotiatedType         string `parquet:"negotiated_type,dict"`
	NegotiatedRate         string `parquet:"negotiated_rate"`
	BillingClass           string `parquet:"billing_class,dict"`
	Setting                string `parquet:"setting,dict"`
	ServiceCode            string `parquet:"service_code,dict"`
	BillingCodeModifier    string `parquet:"billing_code_modifier,dict"`
	ExpirationDate         string `parquet:"expiration_date,dict"`
	SourceFile             string `parquet:"source_file,dict"`
	SourceURL              string `parquet:"source_url,dict"`
	CheckedOn              string `parquet:"checked_on,dict"`
}

// Same columns minus npi, plus the NPI list number and its length (n_npi = flat rows this line stands for).
type lineRow struct {
	ReportingEntityName    string `parquet:"reporting_entity_name,dict"`
	FileLabel              string `parquet:"file_label,dict"`
	LastUpdatedOn          string `parquet:"last_updated_on,dict"`
	BillingCodeType        string `parquet:"billing_code_type,dict"`
	BillingCode            string `parquet:"billing_code,dict"`
	Name                   string `parquet:"name,dict"`
	NegotiationArrangement string `parquet:"negotiation_arrangement,dict"`
	TIN                    string `parquet:"tin"`
	TINType                string `parquet:"tin_type,dict"`
	NegotiatedType         string `parquet:"negotiated_type,dict"`
	NegotiatedRate         string `parquet:"negotiated_rate"`
	BillingClass           string `parquet:"billing_class,dict"`
	Setting                string `parquet:"setting,dict"`
	ServiceCode            string `parquet:"service_code,dict"`
	BillingCodeModifier    string `parquet:"billing_code_modifier,dict"`
	ExpirationDate         string `parquet:"expiration_date,dict"`
	NPISet                 int64  `parquet:"npiset"`
	NNPI                   int64  `parquet:"n_npi"`
	SourceFile             string `parquet:"source_file,dict"`
	SourceURL              string `parquet:"source_url,dict"`
	CheckedOn              string `parquet:"checked_on,dict"`
}

type setRow struct {
	NPISet int64    `parquet:"npiset"`
	NPIs   []string `parquet:"npis,list"`
}

func pqOpts() []parquet.WriterOption {
	return []parquet.WriterOption{
		parquet.Compression(&zstd.Codec{Level: zstd.SpeedDefault}),
		parquet.MaxRowsPerRowGroup(1 << 20),
		parquet.PageBufferSize(1 << 20),
	}
}

// pqFile writes to <path>.part and renames on success, so a crash never leaves a half table behind.
type pqFile struct {
	path string
	f    *os.File
	bw   *bufio.Writer
}

func openPQ(path string) *pqFile {
	f, err := os.Create(path + ".part")
	if err != nil {
		panic(err)
	}
	return &pqFile{path: path, f: f, bw: bufio.NewWriterSize(f, 8<<20)}
}

func (p *pqFile) finish(keep bool) {
	if err := p.bw.Flush(); err != nil {
		panic(err)
	}
	if err := p.f.Close(); err != nil {
		panic(err)
	}
	if keep {
		if err := os.Rename(p.path+".part", p.path); err != nil {
			panic(err)
		}
	} else {
		os.Remove(p.path + ".part")
	}
}

type consts struct{ entity, label, updated, sourceFile, sourceURL, checked string }

func parseConsts(kv []string) consts {
	m := map[string]string{}
	for _, s := range kv {
		k, v, ok := strings.Cut(s, "=")
		if !ok {
			panic("bad -const " + s)
		}
		m[k] = v
	}
	return consts{m["reporting_entity_name"], m["file_label"], m["last_updated_on"], m["source_file"], m["source_url"], m["checked_on"]}
}

type flatSink struct {
	c     consts
	pf    *pqFile
	w     *parquet.GenericWriter[flatRow]
	buf   []flatRow
	nrows int64
}

func newFlatSink(out string, c consts) *flatSink {
	pf := openPQ(out)
	return &flatSink{c: c, pf: pf, w: parquet.NewGenericWriter[flatRow](pf.bw, pqOpts()...)}
}

func (s *flatSink) write(ls []line) {
	s.buf = s.buf[:0]
	for i := range ls {
		l := &ls[i]
		for _, n := range l.set.npis {
			s.buf = append(s.buf, flatRow{s.c.entity, s.c.label, s.c.updated, l.codeType, l.code, l.name, l.arr, n, l.tin, l.ttype,
				l.ntype, l.rate, l.class, l.setting, l.svc, l.mods, l.exp, s.c.sourceFile, s.c.sourceURL, s.c.checked})
		}
	}
	if _, err := s.w.Write(s.buf); err != nil {
		panic(err)
	}
	s.nrows += int64(len(s.buf))
}

func (s *flatSink) close() {
	if err := s.w.Close(); err != nil {
		panic(err)
	}
	s.pf.finish(s.nrows > 0)
}

func (s *flatSink) counts() (int64, int64, int64) { return s.nrows, s.nrows, 0 }

type linesSink struct {
	c                   consts
	pf, ps              *pqFile
	w                   *parquet.GenericWriter[lineRow]
	ws                  *parquet.GenericWriter[setRow]
	ids                 map[[16]byte]int64
	buf                 []lineRow
	sbuf                []setRow
	flat, stored, nsets int64
}

func newLinesSink(out, setsOut string, c consts) *linesSink {
	if setsOut == "" {
		panic("-format lines needs -npisets")
	}
	pf, ps := openPQ(out), openPQ(setsOut)
	return &linesSink{c: c, pf: pf, ps: ps, ids: map[[16]byte]int64{},
		w:  parquet.NewGenericWriter[lineRow](pf.bw, pqOpts()...),
		ws: parquet.NewGenericWriter[setRow](ps.bw, pqOpts()...)}
}

func (s *linesSink) write(ls []line) {
	s.buf, s.sbuf = s.buf[:0], s.sbuf[:0]
	for i := range ls {
		l := &ls[i]
		id, ok := s.ids[l.set.key]
		if !ok {
			id = int64(len(s.ids))
			s.ids[l.set.key] = id
			s.sbuf = append(s.sbuf, setRow{id, l.set.npis})
		}
		n := int64(len(l.set.npis))
		s.buf = append(s.buf, lineRow{s.c.entity, s.c.label, s.c.updated, l.codeType, l.code, l.name, l.arr, l.tin, l.ttype,
			l.ntype, l.rate, l.class, l.setting, l.svc, l.mods, l.exp, id, n, s.c.sourceFile, s.c.sourceURL, s.c.checked})
		s.flat += n
	}
	if _, err := s.w.Write(s.buf); err != nil {
		panic(err)
	}
	if len(s.sbuf) > 0 {
		if _, err := s.ws.Write(s.sbuf); err != nil {
			panic(err)
		}
	}
	s.stored += int64(len(s.buf))
	s.nsets = int64(len(s.ids))
}

func (s *linesSink) close() {
	if err := s.w.Close(); err != nil {
		panic(err)
	}
	if err := s.ws.Close(); err != nil {
		panic(err)
	}
	s.pf.finish(s.stored > 0)
	s.ps.finish(s.stored > 0)
}

func (s *linesSink) counts() (int64, int64, int64) { return s.flat, s.stored, s.nsets }

func newSink(out, format, setsOut string, kv []string) sink {
	if !strings.HasSuffix(out, ".parquet") {
		return newCSVSink(out)
	}
	c := parseConsts(kv)
	switch format {
	case "flat":
		return newFlatSink(out, c)
	case "lines":
		return newLinesSink(out, setsOut, c)
	}
	panic(fmt.Sprintf("unknown -format %q", format))
}
