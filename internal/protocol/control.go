// Package protocol interpreta el campo m: segmentos, control y comando, con los
// errores exactos del original. No conoce HTTP ni estado.
package protocol

// Control devuelve el dígito de control que el original exige para base, el
// texto de m anterior al último ";" (spec INT-01, informe A1):
//
//   - se conservan solo los bytes ASCII [A-Za-z0-9]; el resto, incluido todo
//     byte de UTF-8 multibyte, se descarta antes de cualquier casing (INT-05);
//   - cada letra aporta su posición A=1…Z=26 en decimal y cada dígito su valor,
//     concatenados sin padding (los ceros cuentan como texto, INT-06/07);
//   - a esa cadena se le añaden dos ceros y el control es 98 − resto módulo 97,
//     sin reducción final: rango 2–98.
//
// El resto se acumula dígito a dígito para no construir enteros grandes.
//
// Es el único punto que conoce la fórmula: un plan B (INT-04) solo cambiaría
// esta función.
func Control(base string) int {
	r := 0
	add := func(d int) { r = (r*10 + d) % 97 }
	for i := 0; i < len(base); i++ {
		c := base[i]
		switch {
		case '0' <= c && c <= '9':
			add(int(c - '0'))
		case 'A' <= c && c <= 'Z', 'a' <= c && c <= 'z':
			pos := int(c|0x20-'a') + 1
			if pos >= 10 {
				add(pos / 10)
			}
			add(pos % 10)
		}
	}
	return 98 - r*100%97
}
