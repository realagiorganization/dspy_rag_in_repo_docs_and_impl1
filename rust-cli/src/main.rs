use rusqlite::{params, Connection};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};
use std::time::{SystemTime, UNIX_EPOCH};

const DEFAULT_DB_PATH: &str = "artifacts/sqlite/repo-file-index.sqlite3";
const DEFAULT_LOOKUP_LIMIT: usize = 8;
const DEFAULT_MAX_TEXT_BYTES: u64 = 1_000_000;
const STOP_WORDS: &[&str] = &[
    "a", "an", "and", "are", "as", "at", "be", "by", "does", "for", "from", "how", "in", "into",
    "is", "it", "of", "on", "or", "that", "the", "this", "to", "use", "using", "what", "when",
    "where", "which", "who", "why", "with",
];

#[derive(Debug)]
enum ParsedCommand {
    Delegate(Vec<String>),
    Help,
    Index(IndexConfig),
    Lookup(LookupConfig, String),
}

#[derive(Debug, Clone)]
struct IndexConfig {
    root: PathBuf,
    db_path: PathBuf,
    max_text_bytes: u64,
}

#[derive(Debug, Clone)]
struct LookupConfig {
    root: PathBuf,
    db_path: PathBuf,
    limit: usize,
}

#[derive(Debug, Default)]
struct IndexStats {
    indexed_file_count: usize,
    skipped_binary_count: usize,
    skipped_large_count: usize,
}

fn main() -> ExitCode {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let default_root = manifest_dir.parent().expect("repo root").to_path_buf();
    let args: Vec<String> = env::args().skip(1).collect();

    let parsed = match parse_command(args, &default_root) {
        Ok(command) => command,
        Err(error) => {
            eprintln!("{error}");
            return ExitCode::from(2);
        }
    };

    match parsed {
        ParsedCommand::Help => {
            print_usage(&default_root);
            ExitCode::SUCCESS
        }
        ParsedCommand::Index(config) => match index_repository(&config) {
            Ok(stats) => {
                println!(
                    "db={} indexed={} skipped_binary={} skipped_large={}",
                    display_path(&config.root, &config.db_path),
                    stats.indexed_file_count,
                    stats.skipped_binary_count,
                    stats.skipped_large_count
                );
                ExitCode::SUCCESS
            }
            Err(error) => {
                eprintln!("{error}");
                ExitCode::from(1)
            }
        },
        ParsedCommand::Lookup(config, query_text) => match run_lookup(&config, &query_text) {
            Ok(()) => ExitCode::SUCCESS,
            Err(error) => {
                eprintln!("{error}");
                ExitCode::from(1)
            }
        },
        ParsedCommand::Delegate(args) => delegate_to_uv(&default_root, &args),
    }
}

fn parse_command(args: Vec<String>, default_root: &Path) -> Result<ParsedCommand, String> {
    let Some(command) = args.first() else {
        return Ok(ParsedCommand::Help);
    };

    match command.as_str() {
        "-h" | "--help" | "help" => Ok(ParsedCommand::Help),
        "index" => Ok(ParsedCommand::Index(parse_index_config(
            &args[1..],
            default_root,
        )?)),
        "lookup" => {
            let (config, query_text) = parse_lookup_config(&args[1..], default_root)?;
            Ok(ParsedCommand::Lookup(config, query_text))
        }
        _ => Ok(ParsedCommand::Delegate(args)),
    }
}

fn parse_index_config(args: &[String], default_root: &Path) -> Result<IndexConfig, String> {
    let mut root = default_root.to_path_buf();
    let mut db_path: Option<PathBuf> = None;
    let mut max_text_bytes = DEFAULT_MAX_TEXT_BYTES;
    let mut index = 0;

    while index < args.len() {
        match args[index].as_str() {
            "--help" | "-h" => return Err(index_usage(default_root)),
            "--root" => {
                index += 1;
                let value = args
                    .get(index)
                    .ok_or_else(|| String::from("missing value for --root"))?;
                root = default_root.join(value);
            }
            "--db" => {
                index += 1;
                let value = args
                    .get(index)
                    .ok_or_else(|| String::from("missing value for --db"))?;
                db_path = Some(PathBuf::from(value));
            }
            "--max-bytes" => {
                index += 1;
                let value = args
                    .get(index)
                    .ok_or_else(|| String::from("missing value for --max-bytes"))?;
                max_text_bytes = value
                    .parse()
                    .map_err(|_| format!("invalid --max-bytes value `{value}`"))?;
            }
            unexpected => return Err(format!("unexpected argument for `index`: `{unexpected}`")),
        }
        index += 1;
    }

    root = normalize_root(default_root, &root);
    let db_path = resolve_output_path(&root, db_path);
    Ok(IndexConfig {
        root,
        db_path,
        max_text_bytes,
    })
}

fn parse_lookup_config(
    args: &[String],
    default_root: &Path,
) -> Result<(LookupConfig, String), String> {
    let mut root = default_root.to_path_buf();
    let mut db_path: Option<PathBuf> = None;
    let mut limit = DEFAULT_LOOKUP_LIMIT;
    let mut query_parts: Vec<String> = Vec::new();
    let mut index = 0;

    while index < args.len() {
        match args[index].as_str() {
            "--help" | "-h" => return Err(lookup_usage(default_root)),
            "--root" => {
                index += 1;
                let value = args
                    .get(index)
                    .ok_or_else(|| String::from("missing value for --root"))?;
                root = default_root.join(value);
            }
            "--db" => {
                index += 1;
                let value = args
                    .get(index)
                    .ok_or_else(|| String::from("missing value for --db"))?;
                db_path = Some(PathBuf::from(value));
            }
            "--limit" => {
                index += 1;
                let value = args
                    .get(index)
                    .ok_or_else(|| String::from("missing value for --limit"))?;
                limit = value
                    .parse()
                    .map_err(|_| format!("invalid --limit value `{value}`"))?;
            }
            value => query_parts.push(String::from(value)),
        }
        index += 1;
    }

    if query_parts.is_empty() {
        return Err(String::from("lookup requires a query string"));
    }

    root = normalize_root(default_root, &root);
    let db_path = resolve_output_path(&root, db_path);
    Ok((
        LookupConfig {
            root,
            db_path,
            limit,
        },
        query_parts.join(" "),
    ))
}

fn normalize_root(default_root: &Path, root: &Path) -> PathBuf {
    if root.is_absolute() {
        root.to_path_buf()
    } else {
        default_root.join(root)
    }
}

fn resolve_output_path(root: &Path, maybe_path: Option<PathBuf>) -> PathBuf {
    match maybe_path {
        Some(path) if path.is_absolute() => path,
        Some(path) => root.join(path),
        None => root.join(DEFAULT_DB_PATH),
    }
}

fn print_usage(default_root: &Path) {
    println!(
        "repo-rag-cli index [--root PATH] [--db PATH] [--max-bytes N]\n\
repo-rag-cli lookup [--root PATH] [--db PATH] [--limit N] QUERY\n\
repo-rag-cli <repo-rag args...>\n\
\n\
default root: {}\n\
default db: {}\n\
\n\
`index` builds a SQLite FTS index of tracked UTF-8 text files.\n\
`lookup` refreshes that index when needed and searches path plus content.\n\
Any other subcommand delegates to `uv run repo-rag ...`.",
        default_root.display(),
        default_root.join(DEFAULT_DB_PATH).display()
    );
}

fn index_usage(default_root: &Path) -> String {
    format!(
        "usage: repo-rag-cli index [--root PATH] [--db PATH] [--max-bytes N]\n\
default root: {}\n\
default db: {}",
        default_root.display(),
        default_root.join(DEFAULT_DB_PATH).display()
    )
}

fn lookup_usage(default_root: &Path) -> String {
    format!(
        "usage: repo-rag-cli lookup [--root PATH] [--db PATH] [--limit N] QUERY\n\
default root: {}\n\
default db: {}",
        default_root.display(),
        default_root.join(DEFAULT_DB_PATH).display()
    )
}

fn delegate_to_uv(repo_root: &Path, args: &[String]) -> ExitCode {
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

fn run_lookup(config: &LookupConfig, query_text: &str) -> Result<(), String> {
    let tracked_files = list_tracked_files(&config.root)?;
    ensure_index_is_fresh(&config.root, &config.db_path, &tracked_files)?;
    let match_query = build_match_query(query_text)?;
    let connection = Connection::open(&config.db_path)
        .map_err(|error| format!("failed to open {}: {error}", config.db_path.display()))?;
    let mut statement = connection
        .prepare(
            "SELECT file_lookup.path, indexed_files.line_count, \
             snippet(file_lookup, 1, '[', ']', ' … ', 18), \
             bm25(file_lookup) AS score \
             FROM file_lookup \
             JOIN indexed_files ON indexed_files.path = file_lookup.path \
             WHERE file_lookup MATCH ?1 \
             ORDER BY score, file_lookup.path \
             LIMIT ?2",
        )
        .map_err(|error| format!("failed to prepare lookup statement: {error}"))?;
    let rows = statement
        .query_map(params![match_query, config.limit as i64], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, i64>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, f64>(3)?,
            ))
        })
        .map_err(|error| format!("failed to execute lookup: {error}"))?;

    let mut printed_any = false;
    for (rank, row) in rows.enumerate() {
        let (path, line_count, snippet, score) =
            row.map_err(|error| format!("failed to read lookup row: {error}"))?;
        printed_any = true;
        println!(
            "{}\t{}\tlines={}\tscore={:.3}\t{}",
            rank + 1,
            path,
            line_count,
            score,
            snippet.replace('\n', " ")
        );
    }

    if !printed_any {
        println!("no matches\t{}", query_text.trim());
    }

    Ok(())
}

fn ensure_index_is_fresh(
    root: &Path,
    db_path: &Path,
    tracked_files: &[PathBuf],
) -> Result<(), String> {
    if db_needs_refresh(root, db_path, tracked_files)? {
        let config = IndexConfig {
            root: root.to_path_buf(),
            db_path: db_path.to_path_buf(),
            max_text_bytes: DEFAULT_MAX_TEXT_BYTES,
        };
        index_repository(&config)?;
    }
    Ok(())
}

fn db_needs_refresh(
    root: &Path,
    db_path: &Path,
    tracked_files: &[PathBuf],
) -> Result<bool, String> {
    if !db_path.exists() {
        return Ok(true);
    }

    let db_modified = fs::metadata(db_path)
        .and_then(|metadata| metadata.modified())
        .map_err(|error| format!("failed to stat {}: {error}", db_path.display()))?;
    let connection = Connection::open(db_path)
        .map_err(|error| format!("failed to open {}: {error}", db_path.display()))?;
    let indexed_head = read_meta_value(&connection, "head")?;
    let indexed_tracked_count = read_meta_value(&connection, "tracked_file_count")?;
    let current_head = git_stdout(root, &["rev-parse", "HEAD"])?;

    if indexed_head.as_deref() != Some(current_head.trim()) {
        return Ok(true);
    }
    if indexed_tracked_count.as_deref() != Some(&tracked_files.len().to_string()) {
        return Ok(true);
    }

    for relative_path in tracked_files {
        let absolute_path = root.join(relative_path);
        let metadata = match fs::metadata(&absolute_path) {
            Ok(metadata) => metadata,
            Err(_) => return Ok(true),
        };
        if !metadata.is_file() {
            continue;
        }
        let modified = metadata
            .modified()
            .map_err(|error| format!("failed to stat {}: {error}", absolute_path.display()))?;
        if modified.duration_since(db_modified).is_ok() {
            return Ok(true);
        }
    }

    Ok(false)
}

fn read_meta_value(connection: &Connection, key: &str) -> Result<Option<String>, String> {
    let exists = connection
        .prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'repo_meta'")
        .and_then(|mut statement| statement.exists([]))
        .map_err(|error| format!("failed to inspect SQLite metadata table: {error}"))?;
    if !exists {
        return Ok(None);
    }

    connection
        .query_row(
            "SELECT value FROM repo_meta WHERE key = ?1",
            params![key],
            |row| row.get::<_, String>(0),
        )
        .map(Some)
        .or_else(|error| match error {
            rusqlite::Error::QueryReturnedNoRows => Ok(None),
            other => Err(format!("failed to read SQLite metadata `{key}`: {other}")),
        })
}

fn index_repository(config: &IndexConfig) -> Result<IndexStats, String> {
    let tracked_files = list_tracked_files(&config.root)?;
    if let Some(parent) = config.db_path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("failed to create {}: {error}", parent.display()))?;
    }

    let mut connection = Connection::open(&config.db_path)
        .map_err(|error| format!("failed to open {}: {error}", config.db_path.display()))?;
    connection
        .pragma_update(None, "journal_mode", "WAL")
        .map_err(|error| format!("failed to set SQLite WAL mode: {error}"))?;
    connection
        .pragma_update(None, "synchronous", "NORMAL")
        .map_err(|error| format!("failed to relax SQLite sync mode: {error}"))?;

    let transaction = connection
        .transaction()
        .map_err(|error| format!("failed to start SQLite transaction: {error}"))?;
    transaction
        .execute_batch(
            "DROP TABLE IF EXISTS repo_meta;
             DROP TABLE IF EXISTS indexed_files;
             DROP TABLE IF EXISTS file_lookup;
             CREATE TABLE repo_meta (
                 key TEXT PRIMARY KEY,
                 value TEXT NOT NULL
             );
             CREATE TABLE indexed_files (
                 path TEXT PRIMARY KEY,
                 size_bytes INTEGER NOT NULL,
                 line_count INTEGER NOT NULL
             );
             CREATE VIRTUAL TABLE file_lookup USING fts5(
                 path,
                 content,
                 tokenize = 'unicode61 remove_diacritics 2'
             );",
        )
        .map_err(|error| format!("failed to initialize SQLite schema: {error}"))?;

    let mut stats = IndexStats::default();
    for relative_path in &tracked_files {
        let absolute_path = config.root.join(relative_path);
        let metadata = match fs::metadata(&absolute_path) {
            Ok(metadata) if metadata.is_file() => metadata,
            Ok(_) => continue,
            Err(_) => continue,
        };

        if metadata.len() > config.max_text_bytes {
            stats.skipped_large_count += 1;
            continue;
        }

        let bytes = fs::read(&absolute_path)
            .map_err(|error| format!("failed to read {}: {error}", absolute_path.display()))?;
        if bytes.contains(&0) {
            stats.skipped_binary_count += 1;
            continue;
        }

        let content = match String::from_utf8(bytes) {
            Ok(content) => content,
            Err(_) => {
                stats.skipped_binary_count += 1;
                continue;
            }
        };

        let relative_path_text = relative_path.to_string_lossy().into_owned();
        transaction
            .execute(
                "INSERT INTO indexed_files (path, size_bytes, line_count) VALUES (?1, ?2, ?3)",
                params![
                    relative_path_text,
                    i64::try_from(metadata.len()).unwrap_or(i64::MAX),
                    i64::try_from(count_lines(&content)).unwrap_or(i64::MAX)
                ],
            )
            .map_err(|error| format!("failed to insert indexed file metadata: {error}"))?;
        transaction
            .execute(
                "INSERT INTO file_lookup (path, content) VALUES (?1, ?2)",
                params![relative_path.to_string_lossy().into_owned(), content],
            )
            .map_err(|error| format!("failed to insert SQLite FTS row: {error}"))?;
        stats.indexed_file_count += 1;
    }

    let head = git_stdout(&config.root, &["rev-parse", "HEAD"])?;
    let generated_at = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| format!("failed to read system clock: {error}"))?
        .as_secs()
        .to_string();
    for (key, value) in [
        ("head", head.trim().to_string()),
        ("generated_at_unix", generated_at),
        ("tracked_file_count", tracked_files.len().to_string()),
    ] {
        transaction
            .execute(
                "INSERT INTO repo_meta (key, value) VALUES (?1, ?2)",
                params![key, value],
            )
            .map_err(|error| format!("failed to write SQLite metadata `{key}`: {error}"))?;
    }

    transaction
        .commit()
        .map_err(|error| format!("failed to commit SQLite index: {error}"))?;
    connection
        .execute(
            "INSERT INTO file_lookup(file_lookup) VALUES('optimize')",
            [],
        )
        .map_err(|error| format!("failed to optimize SQLite FTS index: {error}"))?;
    Ok(stats)
}

fn list_tracked_files(root: &Path) -> Result<Vec<PathBuf>, String> {
    let output = Command::new("git")
        .arg("ls-files")
        .arg("--cached")
        .arg("-z")
        .current_dir(root)
        .output()
        .map_err(|error| format!("failed to list tracked files: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "git ls-files failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }

    output
        .stdout
        .split(|byte| *byte == 0)
        .filter(|chunk| !chunk.is_empty())
        .map(|chunk| {
            let text = String::from_utf8(chunk.to_vec())
                .map_err(|error| format!("tracked path is not UTF-8: {error}"))?;
            Ok(PathBuf::from(text))
        })
        .collect()
}

fn git_stdout(root: &Path, args: &[&str]) -> Result<String, String> {
    let output = Command::new("git")
        .args(args)
        .current_dir(root)
        .output()
        .map_err(|error| format!("failed to run git {}: {error}", args.join(" ")))?;
    if !output.status.success() {
        return Err(format!(
            "git {} failed: {}",
            args.join(" "),
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    String::from_utf8(output.stdout).map_err(|error| format!("git output was not UTF-8: {error}"))
}

fn build_match_query(query: &str) -> Result<String, String> {
    let mut tokens: Vec<String> = query
        .split(|character: char| !character.is_alphanumeric())
        .map(|token| token.trim().to_ascii_lowercase())
        .filter(|token| token.len() >= 2)
        .filter(|token| !STOP_WORDS.contains(&token.as_str()))
        .collect();
    tokens.sort();
    tokens.dedup();

    if tokens.is_empty() {
        return Err(String::from(
            "lookup query did not contain any searchable terms",
        ));
    }

    Ok(tokens
        .into_iter()
        .map(|token| format!("{token}*"))
        .collect::<Vec<_>>()
        .join(" AND "))
}

fn count_lines(content: &str) -> usize {
    if content.is_empty() {
        return 0;
    }
    let newline_count = content
        .as_bytes()
        .iter()
        .filter(|byte| **byte == b'\n')
        .count();
    if content.ends_with('\n') {
        newline_count
    } else {
        newline_count + 1
    }
}

fn display_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .map(|relative| relative.display().to_string())
        .unwrap_or_else(|_| path.display().to_string())
}
