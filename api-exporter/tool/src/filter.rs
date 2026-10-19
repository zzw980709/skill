//! 接口筛选：`--include` / `--exclude` / `--endpoints-file` / `--include-tag`。
//!
//! 筛选条目语法（三处通用）：
//!
//! | 写法 | 含义 |
//! | --- | --- |
//! | `path:/user/{id}`、`/user/**` | 按接口 path 筛选（精确，或用 `*`/`**`/`?` 通配） |
//! | `controller:UserController` | 按 Controller 简单名 / 全限定名筛选（子串、忽略大小写） |
//! | `tag:用户管理` | 按 `@Api(tags)` / `@ApiOperation(tags)` 分组筛选（子串、忽略大小写） |
//! | `http:GET` | 按 HTTP 方法筛选 |
//! | `name:getUser` | 按 Java 方法名 / operationId 筛选（子串、忽略大小写） |
//! | `GET /user/{id}` | HTTP 方法 + path 同时满足 |
//!
//! path 匹配规则：不含通配符时要求**完全相等**（`/user` 只命中 `/user`）；
//! 含 `*` / `**` / `?` 时按 glob 匹配（`*` 不跨 `/`，`**` 跨），
//! 所以前缀匹配请写 `path:/user/**`（它同时命中 `/user` 本身）。
//!
//! 多条 `--include` 之间是「或」的关系；`--exclude` 优先级高于 `--include`。

use std::fs;
use std::path::Path;

use anyhow::{bail, Context, Result};

use crate::model::Endpoint;

const HTTP_METHODS: &[&str] = &[
    "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT",
];

/// 一组筛选条件。[`Filter::accepts`] 返回 false 的接口会被直接丢掉。
#[derive(Debug, Clone, Default)]
pub struct Filter {
    only: Vec<Entry>,
    exclude: Vec<Entry>,
}

#[derive(Debug, Clone)]
struct Entry {
    /// 可选的 HTTP 方法约束（`GET /user/{id}` 这种写法）。
    http_method: Option<String>,
    kind: Kind,
    pattern: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Kind {
    /// 匹配所有接口（例如只写了 `--include GET`）。
    Any,
    Path,
    Controller,
    Tag,
    HttpMethod,
    Name,
}

impl Filter {
    /// 从命令行参数构建筛选器；`include_tags` 是历史参数，等价于 `tag:` 条目。
    pub fn build(
        include: &[String],
        exclude: &[String],
        endpoints_file: Option<&Path>,
        include_tags: &[String],
    ) -> Result<Self> {
        let mut only = Vec::new();
        for tag in include_tags {
            if tag.trim().is_empty() {
                continue;
            }
            only.push(Entry {
                http_method: None,
                kind: Kind::Tag,
                pattern: tag.trim().to_string(),
            });
        }
        for spec in include {
            only.push(parse_spec(spec)?);
        }
        if let Some(file) = endpoints_file {
            for (line_no, line) in read_spec_lines(file)? {
                only.push(
                    parse_spec(&line)
                        .with_context(|| format!("{} 第 {} 行", file.display(), line_no))?,
                );
            }
        }
        let mut exclude_entries = Vec::new();
        for spec in exclude {
            exclude_entries.push(parse_spec(spec)?);
        }
        Ok(Self {
            only,
            exclude: exclude_entries,
        })
    }

    pub fn is_empty(&self) -> bool {
        self.only.is_empty() && self.exclude.is_empty()
    }

    pub fn accepts(&self, endpoint: &Endpoint) -> bool {
        let included = self.only.is_empty() || self.only.iter().any(|e| e.matches(endpoint));
        included && !self.exclude.iter().any(|e| e.matches(endpoint))
    }

    pub fn describe(&self) -> String {
        let join = |entries: &[Entry]| {
            entries
                .iter()
                .map(Entry::describe)
                .collect::<Vec<_>>()
                .join(", ")
        };
        match (self.only.is_empty(), self.exclude.is_empty()) {
            (true, true) => "(无)".to_string(),
            (false, true) => format!("只保留 [{}]", join(&self.only)),
            (true, false) => format!("排除 [{}]", join(&self.exclude)),
            (false, false) => format!(
                "只保留 [{}]；排除 [{}]",
                join(&self.only),
                join(&self.exclude)
            ),
        }
    }
}

impl Entry {
    fn matches(&self, endpoint: &Endpoint) -> bool {
        if let Some(method) = &self.http_method {
            if !endpoint.http_method.eq_ignore_ascii_case(method) {
                return false;
            }
        }
        match self.kind {
            Kind::Any => true,
            Kind::Path => path_matches(&self.pattern, &endpoint.path),
            Kind::Controller => matches_any_or(
                &self.pattern,
                &[&endpoint.controller, &endpoint.controller_fqn],
            ),
            Kind::Tag => endpoint
                .tag
                .as_deref()
                .map(|tag| matches_any_or(&self.pattern, &[tag]))
                .unwrap_or(false),
            Kind::HttpMethod => endpoint.http_method.eq_ignore_ascii_case(&self.pattern),
            Kind::Name => matches_any_or(
                &self.pattern,
                &[&endpoint.method_name, &endpoint.operation_id],
            ),
        }
    }

    fn describe(&self) -> String {
        let body = match self.kind {
            Kind::Any => "全部".to_string(),
            Kind::Path => format!("path:{}", self.pattern),
            Kind::Controller => format!("controller:{}", self.pattern),
            Kind::Tag => format!("tag:{}", self.pattern),
            Kind::HttpMethod => format!("http:{}", self.pattern),
            Kind::Name => format!("name:{}", self.pattern),
        };
        match &self.http_method {
            Some(method) => format!("{method} {body}"),
            None => body,
        }
    }
}

/// 解析一条筛选条件。
fn parse_spec(raw: &str) -> Result<Entry> {
    let raw = raw.trim();
    if raw.is_empty() {
        bail!("筛选条件不能为空");
    }

    // "GET /user/{id}"：方法 + 其余部分
    let mut http_method = None;
    let mut rest = raw;
    if let Some((head, tail)) = split_once_whitespace(raw) {
        if is_http_method(head) {
            http_method = Some(head.to_ascii_uppercase());
            rest = tail.trim();
        }
    }
    if rest.is_empty() {
        bail!("`{raw}` 缺少路径");
    }

    let mut kind = Kind::Path;
    let mut pattern = rest.to_string();
    if let Some((prefix, value)) = rest.split_once(':') {
        let prefix = prefix.trim();
        let value = value.trim();
        if is_known_prefix(prefix) && value.is_empty() {
            bail!("`{raw}` 的 `{prefix}:` 后面缺少匹配内容");
        }
        match prefix.to_ascii_lowercase().as_str() {
            "path" | "url" => {
                kind = Kind::Path;
                pattern = value.to_string();
            }
            "controller" | "class" => {
                kind = Kind::Controller;
                pattern = value.to_string();
            }
            "tag" | "group" => {
                kind = Kind::Tag;
                pattern = value.to_string();
            }
            "http" | "method" => {
                kind = Kind::HttpMethod;
                pattern = value.to_ascii_uppercase();
            }
            "name" => {
                kind = Kind::Name;
                pattern = value.to_string();
            }
            // 不认识的 `xxx:yyy` 整体当成路径，避免误伤带冒号的写法
            _ => {}
        }
    }

    // 只写了 "GET" 这种：等价于 --include http:GET
    if http_method.is_none() && kind == Kind::Path && is_http_method(rest) {
        http_method = Some(rest.to_ascii_uppercase());
        kind = Kind::Any;
        pattern = String::new();
    }
    if kind == Kind::HttpMethod && !is_http_method(&pattern) {
        let allowed = HTTP_METHODS.join("/");
        bail!("`{raw}` 不是合法的 HTTP 方法，可用: {allowed}");
    }

    Ok(Entry {
        http_method,
        kind,
        pattern,
    })
}

fn split_once_whitespace(value: &str) -> Option<(&str, &str)> {
    let idx = value.find(char::is_whitespace)?;
    Some((&value[..idx], &value[idx..]))
}

fn is_http_method(value: &str) -> bool {
    HTTP_METHODS.iter().any(|m| m.eq_ignore_ascii_case(value))
}

fn is_known_prefix(prefix: &str) -> bool {
    matches!(
        prefix.to_ascii_lowercase().as_str(),
        "path" | "url" | "controller" | "class" | "tag" | "group" | "http" | "method" | "name"
    )
}

fn contains_ci(haystack: &str, needle: &str) -> bool {
    haystack.to_lowercase().contains(&needle.to_lowercase())
}

/// 子串匹配；`*` 表示「任意」（例如 `controller:*` 等于全部控制器）。
fn matches_any_or(pattern: &str, values: &[&str]) -> bool {
    pattern == "*" || values.iter().any(|v| contains_ci(v, pattern))
}

fn read_spec_lines(file: &Path) -> Result<Vec<(usize, String)>> {
    let text = fs::read_to_string(file).with_context(|| format!("读取 {} 失败", file.display()))?;
    let mut lines = Vec::new();
    for (idx, raw) in text.lines().enumerate() {
        let line = raw.split(" #").next().unwrap_or(raw).trim();
        if line.is_empty() || line.starts_with('#') || line.starts_with("//") {
            continue;
        }
        lines.push((idx + 1, line.to_string()));
    }
    Ok(lines)
}

/// path 匹配：无通配符要求完全相等，有通配符按 glob。
pub fn path_matches(pattern: &str, path: &str) -> bool {
    let pattern = normalize_pattern(pattern);
    if pattern.is_empty() {
        return true;
    }
    if !pattern.contains('*') && !pattern.contains('?') {
        return path == pattern;
    }
    // "/user/**" 也应该命中 "/user" 本身
    if let Some(base) = pattern.strip_suffix("/**") {
        if path == base {
            return true;
        }
    }
    let pattern_chars: Vec<char> = pattern.chars().collect();
    let path_chars: Vec<char> = path.chars().collect();
    glob_match(&pattern_chars, &path_chars)
}

fn normalize_pattern(pattern: &str) -> String {
    let mut p = pattern.trim().to_string();
    if p.is_empty() {
        return String::new();
    }
    if !p.starts_with('/') {
        p.insert(0, '/');
    }
    while p.len() > 1 && p.ends_with('/') {
        p.pop();
    }
    p
}

fn glob_match(pattern: &[char], text: &[char]) -> bool {
    let Some((&first, rest)) = pattern.split_first() else {
        return text.is_empty();
    };
    match first {
        '*' => {
            let double = rest.first() == Some(&'*');
            let rest = if double { &rest[1..] } else { rest };
            let mut consumed = 0;
            loop {
                if glob_match(rest, &text[consumed..]) {
                    return true;
                }
                if consumed == text.len() {
                    return false;
                }
                // 单星不跨路径段
                if !double && text[consumed] == '/' {
                    return false;
                }
                consumed += 1;
            }
        }
        '?' => !text.is_empty() && text[0] != '/' && glob_match(rest, &text[1..]),
        _ => text.first() == Some(&first) && glob_match(rest, &text[1..]),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn endpoint(class: &str, method: &str, http: &str, path: &str) -> Endpoint {
        Endpoint {
            controller: class.to_string(),
            controller_fqn: format!("com.demo.{class}"),
            method_name: method.to_string(),
            operation_id: format!("{class}_{method}"),
            http_method: http.to_string(),
            path: path.to_string(),
            ..Default::default()
        }
    }

    #[test]
    fn path_exact_and_glob() {
        // 无通配符 = 精确匹配
        assert!(path_matches("/user", "/user"));
        assert!(!path_matches("/user", "/user/list"));
        assert!(!path_matches("/user", "/user/{id}"));
        assert!(!path_matches("/user", "/userInfo"));
        assert!(!path_matches("/", "/anything"));
        assert!(path_matches("/", "/"));
        // 通配符 = glob，"/user/**" 也命中 "/user" 本身
        assert!(path_matches("/user/**", "/user"));
        assert!(path_matches("/user/**", "/user/{id}/detail"));
        assert!(!path_matches("/user/**", "/userInfo"));
        assert!(path_matches("/api/*/detail", "/api/user/detail"));
        assert!(!path_matches("/api/*/detail", "/api/user/inner/detail"));
        assert!(path_matches("/api/**/detail", "/api/user/inner/detail"));
        assert!(path_matches("/**", "/anything/at/all"));
    }

    #[test]
    fn parse_specs() {
        let entry = parse_spec("GET /user/{id}").unwrap();
        assert_eq!(entry.http_method.as_deref(), Some("GET"));
        assert_eq!(entry.kind, Kind::Path);
        assert_eq!(entry.pattern, "/user/{id}");

        let entry = parse_spec("path:/order/**").unwrap();
        assert_eq!(entry.kind, Kind::Path);
        assert_eq!(entry.pattern, "/order/**");

        let entry = parse_spec("controller:UserController").unwrap();
        assert_eq!(entry.kind, Kind::Controller);

        let entry = parse_spec("tag:用户").unwrap();
        assert_eq!(entry.kind, Kind::Tag);

        let entry = parse_spec("http:post").unwrap();
        assert_eq!(entry.kind, Kind::HttpMethod);
        assert_eq!(entry.pattern, "POST");

        let entry = parse_spec("name:getUser").unwrap();
        assert_eq!(entry.kind, Kind::Name);

        let entry = parse_spec("GET").unwrap();
        assert_eq!(entry.http_method.as_deref(), Some("GET"));
        assert_eq!(entry.kind, Kind::Any);

        // 子串匹配可以用 * 表示「任意」
        let entry = parse_spec("controller:*").unwrap();
        assert_eq!(entry.kind, Kind::Controller);
        assert!(entry.matches(&endpoint("UserController", "getUser", "GET", "/user")));

        // 未知前缀整体当路径
        let entry = parse_spec("/a:b/c").unwrap();
        assert_eq!(entry.kind, Kind::Path);
        assert_eq!(entry.pattern, "/a:b/c");

        assert!(parse_spec("").is_err());
        assert!(parse_spec("http:whatever").is_err());
        assert!(parse_spec("controller:").is_err());
    }
}
