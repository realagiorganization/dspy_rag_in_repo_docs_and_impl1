use std::env;
use std::path::PathBuf;
use std::process::{Command, ExitCode};

fn main() -> ExitCode {
    let args: Vec<String> = env::args().skip(1).collect();
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = manifest_dir.parent().expect("repo root");

    let status = Command::new("uv")
        .arg("run")
        .arg("repo-rag")
        .args(args)
        .current_dir(repo_root)
        .status();

    match status {
        Ok(exit_status) if exit_status.success() => ExitCode::SUCCESS,
        Ok(exit_status) => ExitCode::from(exit_status.code().unwrap_or(1) as u8),
        Err(error) => {
            eprintln!("failed to execute uv-managed workflow: {error}");
            ExitCode::from(1)
        }
    }
}
