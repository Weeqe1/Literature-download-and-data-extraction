# Stage 1: Paper Metadata Extraction

You are extracting **basic bibliographic metadata** from a scientific paper about nano fluorescent probes.

## Task
Extract the paper metadata. Return a JSON object with these exact keys.

## Fields to Extract

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Paper title |
| `doi` | string | DOI identifier (e.g., 10.1234/xxx) |
| `year` | integer | Publication year |
| `journal` | string | Journal name |
| `first_author` | string | First author name |
| `corresponding_author` | string | Corresponding author name |
| `sample_count` | integer | Number of distinct probe samples described in the paper |

## Response Format

Return ONLY valid JSON:
```json
{
  "title": "...",
  "doi": "...",
  "year": 2024,
  "journal": "...",
  "first_author": "...",
  "corresponding_author": "...",
  "sample_count": 3
}
```

If a field cannot be found, use `null`.
