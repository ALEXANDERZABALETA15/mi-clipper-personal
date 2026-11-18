"""Pruebas del editor vertical. Ejecutar: python -m unittest discover -s tests."""

import unittest

import editor_vertical


class TestEditorVertical(unittest.TestCase):
    def test_convierte_porcentajes_a_pixeles(self):
        rect = {"x": 50, "y": 10, "ancho": 25, "alto": 30}
        self.assertEqual(editor_vertical.rectangulo_a_pixeles(rect, 1920, 1080), (960, 108, 480, 324))

    def test_ajusta_coordenadas_a_pares(self):
        rect = {"x": 1, "y": 1, "ancho": 30, "alto": 30}
        x, y, ancho, alto = editor_vertical.rectangulo_a_pixeles(rect, 1919, 1079)
        self.assertEqual((x % 2, y % 2, ancho % 2, alto % 2), (0, 0, 0, 0))

    def test_rechaza_rectangulo_fuera_del_video(self):
        rect = {"x": 80, "y": 0, "ancho": 30, "alto": 30}
        with self.assertRaises(editor_vertical.ErrorEditorVertical):
            editor_vertical.rectangulo_a_pixeles(rect, 1920, 1080)

    def test_rechaza_rectangulo_sin_area(self):
        rect = {"x": 0, "y": 0, "ancho": 0, "alto": 30}
        with self.assertRaises(editor_vertical.ErrorEditorVertical):
            editor_vertical.rectangulo_a_pixeles(rect, 1920, 1080)

    def test_valida_configuracion_editor(self):
        config = {
            "gameplay": {"x": 0, "y": 0, "ancho": 100, "alto": 100},
            "camara": {"x": 70, "y": 5, "ancho": 25, "alto": 30},
            "camara_posicion": "Superior",
            "camara_alineacion": "Derecha",
            "camara_ancho": 45,
        }
        editor_vertical.validar_configuracion(config)

    def test_rechaza_tamano_de_camara_fuera_de_rango(self):
        config = {
            "gameplay": {"x": 0, "y": 0, "ancho": 100, "alto": 100},
            "camara": {"x": 70, "y": 5, "ancho": 25, "alto": 30},
            "camara_ancho": 90,
        }
        with self.assertRaises(editor_vertical.ErrorEditorVertical):
            editor_vertical.validar_configuracion(config)


if __name__ == "__main__":
    unittest.main()
