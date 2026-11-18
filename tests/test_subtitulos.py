"""Pruebas unitarias del generador SRT. Ejecutar: python -m unittest discover -s tests."""

import unittest

import subtitulos


class TestSubtitulosSRT(unittest.TestCase):
    def test_tiempos_se_ajustan_al_inicio_del_clip(self):
        segmentos = [
            {"inicio": 12.0, "fin": 14.0, "texto": "Hola, estamos probando."},
            {"inicio": 14.1, "fin": 16.0, "texto": "Este es el segundo subtítulo."},
        ]
        srt = subtitulos.crear_srt(segmentos, 12.0, 16.0)
        self.assertIn("00:00:00,000 -->", srt)
        self.assertIn("Hola, estamos probando.", srt)
        self.assertIn("Este es el segundo subtítulo.", srt)

    def test_ignora_segmentos_fuera_del_clip(self):
        segmentos = [
            {"inicio": 1.0, "fin": 2.0, "texto": "Antes"},
            {"inicio": 5.0, "fin": 7.0, "texto": "Dentro"},
            {"inicio": 12.0, "fin": 13.0, "texto": "Después"},
        ]
        srt = subtitulos.crear_srt(segmentos, 5.0, 8.0)
        self.assertIn("Dentro", srt)
        self.assertNotIn("Antes", srt)
        self.assertNotIn("Después", srt)

    def test_divide_texto_largo_en_bloques_legibles(self):
        texto = "Esta es una frase bastante larga que debe dividirse para facilitar la lectura en pantalla."
        srt = subtitulos.crear_srt(
            [{"inicio": 0.0, "fin": 5.0, "texto": texto}],
            0.0,
            5.0,
            max_caracteres=25,
        )
        self.assertIn("Esta es una frase", srt)
        self.assertGreaterEqual(srt.count("-->"), 2)

    def test_rechaza_clip_sin_duracion(self):
        with self.assertRaises(subtitulos.ErrorSubtitulos):
            subtitulos.crear_srt([], 5.0, 5.0)

    def test_rechaza_clip_sin_transcripcion(self):
        with self.assertRaises(subtitulos.ErrorSubtitulos):
            subtitulos.crear_srt([], 0.0, 10.0)


if __name__ == "__main__":
    unittest.main()
