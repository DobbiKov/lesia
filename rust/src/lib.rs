use pyo3::prelude::*;

#[pyfunction]
fn hello() -> &'static str {
    "hello from rust"
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(hello, m)?)?;
    Ok(())
}
