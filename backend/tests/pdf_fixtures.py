"""Synthetic PDF builders for tests (no new dependency).

`positioned_pdf()` places every line with its own absolute x/y (a `Td`
per line, no literal leading spaces), which is how LaTeX listings and most
lab-manual generators lay out code. pypdf's default extraction therefore
loses the indentation -- the same behaviour seen on a real pdfTeX lab PDF --
while its layout mode can recover it.

All content in the fixtures below is invented for testing.
"""

from __future__ import annotations

# A line is (indent_levels, text, is_code). 1 indent level = 4 spaces of
# source code = 18 pt of horizontal offset.
Line = tuple[int, str, bool]

_LEFT = 72
_STEP = 18
_TOP = 780
_LEADING = 13


def _escape(text: str) -> bytes:
    cleaned = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return cleaned.encode("latin-1", "replace")


def positioned_pdf(pages: list[list[Line]]) -> bytes:
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")  # placeholder, filled below
    pages_obj = add(b"")
    font_text = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font_code = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")

    page_ids: list[int] = []
    for lines in pages:
        ops: list[bytes] = [b"BT"]
        y = _TOP
        previous_x = 0
        previous_y = 0
        for indent, text, is_code in lines:
            x = _LEFT + indent * _STEP
            if text:
                font = b"/F2 10 Tf" if is_code else b"/F1 11 Tf"
                ops.append(font)
                ops.append(b"%d %d Td" % (x - previous_x, y - previous_y))
                ops.append(b"(" + _escape(text) + b") Tj")
                previous_x, previous_y = x, y
            y -= _LEADING
        ops.append(b"ET")
        stream = b"\n".join(ops)
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page = add(
            (
                f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 {font_text} 0 R /F2 {font_code} 0 R >> >> "
                f"/Contents {content} 0 R >>"
            ).encode()
        )
        page_ids.append(page)

    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode()
    kids = " ".join(f"{i} 0 R" for i in page_ids)
    objects[pages_obj - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()

    out = b"%PDF-1.4\n"
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += (
        b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, catalog, xref)
    )
    return out


def _t(text: str) -> Line:
    return (0, text, False)


def _c(indent: int, text: str) -> Line:
    return (indent, text, True)


# --- A synthetic parallel-programming lab manual: Programs 1-4, one per page
# (Program 3 deliberately continues onto a second page), each with an aim,
# code, output and notes. Mirrors the structure of a typical lab PDF.
LAB_MANUAL_PAGES: list[list[Line]] = [
    [
        _t("Parallel Programming Lab Manual"),
        _t("Programs 1 to 4"),
        _t(""),
        _t("Program 1: Hello from every process"),
        _t("Aim: print a greeting from each MPI process together with its rank."),
        _t(""),
        _c(0, "#include <mpi.h>"),
        _c(0, "#include <stdio.h>"),
        _c(0, "int main(int argc, char *argv[]) {"),
        _c(1, "int rank, size;"),
        _c(1, "MPI_Init(&argc, &argv);"),
        _c(1, "MPI_Comm_rank(MPI_COMM_WORLD, &rank);"),
        _c(1, "MPI_Comm_size(MPI_COMM_WORLD, &size);"),
        _c(1, 'printf("Hello from rank %d of %d\\n", rank, size);'),
        _c(1, "MPI_Finalize();"),
        _c(1, "return 0;"),
        _c(0, "}"),
        _t(""),
        _t("Output (run with 3 processes):"),
        _c(0, "Hello from rank 0 of 3"),
        _c(0, "Hello from rank 1 of 3"),
        _c(0, "Hello from rank 2 of 3"),
        _t("Note: the order of the lines can differ between runs."),
    ],
    [
        _t("Program 2: Sum of an array with MPI_Reduce"),
        _t("Aim: add the numbers 1 to 8 using several processes and print the total on rank 0."),
        _t(""),
        _c(0, "#include <mpi.h>"),
        _c(0, "#include <stdio.h>"),
        _c(0, "int main(int argc, char *argv[]) {"),
        _c(1, "int rank, local = 0, total = 0;"),
        _c(1, "MPI_Init(&argc, &argv);"),
        _c(1, "MPI_Comm_rank(MPI_COMM_WORLD, &rank);"),
        _c(1, "for (int i = rank * 2 + 1; i <= rank * 2 + 2; i++) {"),
        _c(2, "local += i;"),
        _c(1, "}"),
        _c(1, "MPI_Reduce(&local, &total, 1, MPI_INT, MPI_SUM, 0, MPI_COMM_WORLD);"),
        _c(1, "if (rank == 0) {"),
        _c(2, 'printf("Total = %d\\n", total);'),
        _c(1, "}"),
        _c(1, "MPI_Finalize();"),
        _c(1, "return 0;"),
        _c(0, "}"),
        _t(""),
        _t("Output (run with 4 processes):"),
        _c(0, "Total = 36"),
        _t("Concept: MPI_Reduce combines one value from every process using an operation."),
    ],
    [
        _t("Program 3: Bubble sort"),
        _t("Aim: sort an array of integers in ascending order using bubble sort."),
        _t(""),
        _c(0, "#include <stdio.h>"),
        _c(0, "void bubble_sort(int a[], int n) {"),
        _c(1, "for (int i = 0; i < n - 1; i++) {"),
        _c(2, "for (int j = 0; j < n - i - 1; j++) {"),
        _c(3, "if (a[j] > a[j + 1]) {"),
        _c(4, "int t = a[j];"),
        _c(4, "a[j] = a[j + 1];"),
        _c(4, "a[j + 1] = t;"),
        _c(3, "}"),
        _c(2, "}"),
        _c(1, "}"),
        _c(0, "}"),
    ],
    [
        _c(0, "int main(void) {"),
        _c(1, "int a[5] = {5, 1, 4, 2, 8};"),
        _c(1, "bubble_sort(a, 5);"),
        _c(1, "for (int i = 0; i < 5; i++) {"),
        _c(2, 'printf("%d ", a[i]);'),
        _c(1, "}"),
        _c(1, "return 0;"),
        _c(0, "}"),
        _t(""),
        _t("Output:"),
        _c(0, "1 2 4 5 8"),
        _t("Concept: after each pass the largest remaining element moves to the end."),
        _t(""),
        _t("Program 4: Factorial using recursion"),
        _t("Aim: compute n! recursively."),
        _c(0, "long fact(int n) {"),
        _c(1, "if (n <= 1) {"),
        _c(2, "return 1;"),
        _c(1, "}"),
        _c(1, "return n * fact(n - 1);"),
        _c(0, "}"),
        _t("Output for n = 5:"),
        _c(0, "120"),
    ],
]


def lab_manual_pdf() -> bytes:
    return positioned_pdf(LAB_MANUAL_PAGES)
