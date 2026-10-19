//! api-exporter：扫描 Spring Boot 源码 -> OpenAPI 3.0 -> Apifox

mod apifox;
mod cli;
mod config;
mod filter;
mod java;
mod model;
mod openapi;
mod schema;

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use anyhow::{bail, Context, Result};
use clap::Parser;

use crate::model::Endpoint;

fn main() {
    let args = cli::Args::parse();
    if let Err(err) = run(&args) {
        eprintln!("[error] {err:#}");
        if args.verbose {
            eprintln!("{err:?}");
        }
        std::process::exit(1);
    }
}

fn run(args: &cli::Args) -> Result<()> {
    let project_dir = args
        .project
        .canonicalize()
        .unwrap_or_else(|_| args.project.clone());
    let source_root = project_dir.join("src/main/java");
    if !source_root.is_dir() {
        bail!("找不到源码目录: {}", source_root.display());
    }

    if args.verbose {
        println!("[info] 项目目录 : {}", project_dir.display());
        println!("[info] profile  : {}", args.profile);
    }

    // 1. 解析所有源码
    let project = java::project::Project::scan(&source_root)?;

    // 2. 生成 endpoints（同时登记 components）；筛选在解析参数前生效
    let filter = filter::Filter::build(
        &args.include,
        &args.exclude,
        args.endpoints_file.as_deref(),
        &args.include_tags,
    )?;
    if args.verbose && !filter.is_empty() {
        println!("[info] 筛选条件 : {}", filter.describe());
    }
    let mut builder = schema::SchemaBuilder::new(&project);
    let (endpoints, scanned_endpoints) = {
        let mut auditor = java::controllers::Auditor::new(&project, &mut builder);
        auditor.analyze(&filter)
    };
    if !filter.is_empty() {
        println!(
            "[info] 接口筛选 : 保留 {} / {} 条  ({})",
            endpoints.len(),
            scanned_endpoints,
            filter.describe()
        );
    }

    // --list：只看清单，不生成文件
    if args.list {
        print_listing(&endpoints);
        return Ok(());
    }
    if endpoints.is_empty() && !filter.is_empty() {
        println!("[warn] 筛选后没有任何接口，生成的文档会是空的");
        println!("       可先用 --list 查看清单");
        println!("       path 不带通配符时是精确匹配，前缀请写 path:/user/**");
    }

    // 3. 读取 context-path / port
    let server = config::read_server_config(&project_dir, &args.profile, args.config.as_deref());
    let context_path = args
        .context_path
        .clone()
        .unwrap_or_else(|| server.context_path.clone());
    let port = args.port.or(server.port).unwrap_or(8080);
    let server_url = args.base_url.clone().unwrap_or_else(|| {
        format!("{}://{}:{}{}", args.scheme, args.host, port, context_path)
    });

    let title = args.title.clone().unwrap_or_else(|| {
        project_dir
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_else(|| "API".to_string())
    });

    // 4. 生成 OpenAPI
    let openapi_config = openapi::OpenApiConfig {
        title,
        version: args.api_version.clone(),
        server_url: server_url.clone(),
        context_path: context_path.clone(),
        prepend_context_path: args.prepend_context_path,
    };
    let document = openapi::generate(&endpoints, &builder, &openapi_config);

    // 5. 写文件（--out 支持文件路径，也支持目录，目录下自动写 openapi.json）
    let out = resolve_out_path(args.out.as_deref(), &project_dir);
    if let Some(parent) = out.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let json = serde_json::to_string_pretty(&document)?;
    std::fs::write(&out, &json).with_context(|| format!("写入 {} 失败", out.display()))?;

    // 6. 摘要
    let model_count = document
        .pointer("/components/schemas")
        .and_then(|v| v.as_object())
        .map(|o| o.len())
        .unwrap_or(0);
    let pruned_models = builder.components().len().saturating_sub(model_count);
    println!("=========================================================");
    println!("api-exporter 完成");
    println!("  扫描类型   : {} 个 (解析失败 {})", project.by_fqn.len(), project.parse_errors);
    println!("  接口数量   : {}", endpoints.len());
    println!(
        "  数据模型   : {model_count} 个{}",
        if pruned_models > 0 {
            format!("（剔除未被引用 {pruned_models} 个）")
        } else {
            String::new()
        }
    );
    println!(
        "  context-path: {}   [{}]",
        if context_path.is_empty() { "(空)" } else { &context_path },
        server.describe()
    );
    println!("  servers    : {server_url}");
    println!("  输出文件   : {}", out.display());
    println!("=========================================================");
    print_breakdown(&endpoints);

    // 7. 推送 Apifox
    if args.dry_run {
        println!("[info] --dry-run，跳过推送 Apifox");
    } else if let (Some(token), Some(project_id)) = (args.apifox_token.as_ref(), args.apifox_project) {
        push_apifox(args, token, project_id, &json)?;
    } else {
        println!("[info] 未提供 Apifox token / project，仅生成文件。");
        println!("       推送示例: --apifox-token <token> --apifox-project <id>");
    }

    Ok(())
}

/// 解析 `--out`：
/// * 未传 -> `<project>/build/apifox/openapi.json`
/// * 传的是目录（已存在，或以 `/` 结尾）-> 在该目录下写 `openapi.json`
/// * 其余按文件路径处理
fn resolve_out_path(requested: Option<&Path>, project_dir: &Path) -> PathBuf {
    const FILE_NAME: &str = "openapi.json";
    let Some(path) = requested else {
        return project_dir.join("build/apifox").join(FILE_NAME);
    };
    let raw = path.to_string_lossy();
    let trailing_separator = raw.ends_with('/') || raw.ends_with(std::path::MAIN_SEPARATOR);
    if path.is_dir() || trailing_separator {
        path.join(FILE_NAME)
    } else {
        path.to_path_buf()
    }
}

fn print_breakdown(endpoints: &[Endpoint]) {
    let mut by_method: BTreeMap<String, usize> = BTreeMap::new();
    let mut by_tag: BTreeMap<String, usize> = BTreeMap::new();
    for endpoint in endpoints {
        *by_method.entry(endpoint.http_method.clone()).or_default() += 1;
        *by_tag
            .entry(endpoint.tag.clone().unwrap_or_else(|| "(未分组)".to_string()))
            .or_default() += 1;
    }
    println!("按方法统计: {by_method:?}");
    println!("分组数量  : {}", by_tag.len());
    println!("全部分组  : {:?}", by_tag.keys().collect::<Vec<_>>());
}

/// `--list`：列出筛选后的接口清单，方便挑选出要导出的接口。
fn print_listing(endpoints: &[Endpoint]) {
    if endpoints.is_empty() {
        println!("[warn] 没有匹配的接口，请检查 --include / --exclude / --include-tag");
        return;
    }
    println!("[info] 匹配到 {} 条接口", endpoints.len());
    println!();

    let index_w = endpoints.len().to_string().len().max(1);
    let method_w = endpoints
        .iter()
        .map(|e| display_width(&e.http_method))
        .max()
        .unwrap_or(0)
        .max(2);
    let path_w = endpoints
        .iter()
        .map(|e| display_width(&e.path))
        .max()
        .unwrap_or(0)
        .max(2);
    let tag_w = endpoints
        .iter()
        .map(|e| display_width(e.tag.as_deref().unwrap_or("")))
        .max()
        .unwrap_or(0)
        .max(2);
    let handler_w = endpoints
        .iter()
        .map(|e| display_width(&format!("{}.{}", e.controller, e.method_name)))
        .max()
        .unwrap_or(0)
        .max(4);

    println!(
        "{:<index_w$}  {}  {}  {}  {}  摘要",
        "#",
        pad("方法", method_w),
        pad("路径", path_w),
        pad("分组", tag_w),
        pad("处理器", handler_w),
    );
    for (idx, endpoint) in endpoints.iter().enumerate() {
        let handler = format!("{}.{}", endpoint.controller, endpoint.method_name);
        println!(
            "{:<index_w$}  {}  {}  {}  {}  {}",
            idx + 1,
            pad(&endpoint.http_method, method_w),
            pad(&endpoint.path, path_w),
            pad(endpoint.tag.as_deref().unwrap_or(""), tag_w),
            pad(&handler, handler_w),
            endpoint.summary.as_deref().unwrap_or(""),
        );
    }
    println!();
    if let Some(first) = endpoints.first() {
        println!(
            "[tip] 导出单条接口: --include \"{} {}\"",
            first.http_method, first.path
        );
    }
    println!("[tip] 导出某个前缀: --include path:/user/**    按控制器: --include controller:UserController");
    println!("[tip] 批量导出    : 把上面的接口写进文件（每行一条），再加 --endpoints-file <file>");
}

/// 终端显示宽度（CJK 与全角字符占两格）。
fn display_width(text: &str) -> usize {
    text.chars()
        .map(|c| if is_wide_char(c) { 2 } else { 1 })
        .sum()
}

fn is_wide_char(c: char) -> bool {
    matches!(c,
        '\u{1100}'..='\u{115F}'
        | '\u{2E80}'..='\u{A4CF}'
        | '\u{AC00}'..='\u{D7A3}'
        | '\u{F900}'..='\u{FAFF}'
        | '\u{FE30}'..='\u{FE6F}'
        | '\u{FF00}'..='\u{FF60}'
        | '\u{FFE0}'..='\u{FFE6}'
        | '\u{20000}'..='\u{2FFFD}')
}

fn pad(text: &str, width: usize) -> String {
    let actual = display_width(text);
    if actual >= width {
        text.to_string()
    } else {
        format!("{text}{}", " ".repeat(width - actual))
    }
}

fn push_apifox(args: &cli::Args, token: &str, project_id: u64, json: &str) -> Result<()> {
    let schema_mode = if args.apifox_mode == "AUTO_MERGE" {
        "AUTO_MERGE".to_string()
    } else {
        args.apifox_mode.clone()
    };
    let options = apifox::ImportOptions {
        endpoint_overwrite_behavior: args.apifox_mode.clone(),
        schema_overwrite_behavior: schema_mode,
        delete_unmatched_resources: args.delete_unmatched,
        target_endpoint_folder_id: args.apifox_folder,
        target_branch_id: args.apifox_branch,
        ..Default::default()
    };
    println!(
        "[info] 正在推送到 Apifox 项目 {} (mode={}) ...",
        project_id, args.apifox_mode
    );
    let result = apifox::import_openapi(project_id, token, json, &options)?;
    println!("[apifox] {result}");
    if !result.success {
        bail!("推送失败: {}", result.raw_body);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn out_path_resolution() {
        let project = Path::new("/tmp/demo-project");

        // 默认路径
        assert_eq!(
            resolve_out_path(None, project),
            PathBuf::from("/tmp/demo-project/build/apifox/openapi.json")
        );
        // 以 / 结尾的目录（不存在也会被创建）
        assert_eq!(
            resolve_out_path(Some(Path::new("/tmp/dist/")), project),
            PathBuf::from("/tmp/dist/openapi.json")
        );
        // 已存在的目录
        let tmp = std::env::temp_dir();
        assert_eq!(
            resolve_out_path(Some(&tmp), project),
            tmp.join("openapi.json")
        );
        // 文件路径原样
        assert_eq!(
            resolve_out_path(Some(Path::new("/tmp/api.json")), project),
            PathBuf::from("/tmp/api.json")
        );
    }
}
