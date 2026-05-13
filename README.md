# Assumptions

- CSV files fit into memory for this assignment scope
- Exact duplicate detection is sufficient
- Suspicious reports are accepted instead of rejected
- Validation rules are configurable business rules
- Medical thresholds are guidance values, not diagnoses

# Trade-offs

| Decision                   | Tradeoff                               |
| -------------------------- | -------------------------------------- |
| Synchronous processing     | simpler but slower for huge files      |
| SHA256 exact deduplication | fast but not fuzzy matching            |
| Store raw rows             | more storage but full auditability     |
| Strict validation          | cleaner data but higher rejection rate |

# What does the backed supports?
The backend now exposes:

POST /upload
Upload and process CBC CSV reports with:
    Validation
    Data normalization
    Deduplication
    Suspicious report detection

GET /upload/template
Retrieve:
    Required CSV column structure
    Example upload format
    
GET /uploads/{upload_id}
Fetch upload investigation details including:
    Processing summary
    Rejected rows
    Validation failures

GET /reports
Retrieve processed CBC reports with support for:
    Filtering
    Searching
    Sorting
    Suspicious-only queries
    Pagination

GET /analytics
Retrieve aggregated analytics including:
    Abnormal report counts
    Suspicious report statistics
    Rejection summaries
    Upload metrics

# Technologies and modules used



# Database Setup
1. login to your mysql with your password
2. CREATE DATABASE medical_reports;

# IF USING DOCKER
    
    0. Download and set up docker in you machine.

    1. Set the medical-report-system/backend/.env file to:
        DATABASE_URL=mysql+pymysql://user:YOURPASSWORD@host.docker.internal:3306/medical_reports
    2. docker compose down 
    3. docker compose up --build

# IF NOT USING DOCKER

    1. Set the medical-report-system/backend/.env file to:
        DATABASE_URL=mysql+pymysql://user:YOURPASSWORD@localhost:3306/medical_reports

# Backend Setup
1. Download the .zip file for the project
2. unzip it.
3. Update your correct password of mysql at medical-report-system/backend/.env
4. cd medical-report-system/backend
Optional : set up your virtual environment to instal the dependencies safely.
5. pip install -r requirements.txt
6. Run the backend using : uvicorn app.main:app --reload
    Our backend should run at:
    http://127.0.0.1:8000

    We can test:
    http://127.0.0.1:8000/docs

# Frontend Setup
1. cd medical-report-system/frontend
2. npm install
3. npm run dev
4. React frontend should run at:
    Copyhttp://localhost:5173

    
# High Level Flow

    CSV Upload
        ↓
    uploads
        ↓
    raw_report_rows
        ↓ validation
┌───────────────┴───────────────┐
↓                               ↓
cbc_reports               rejected_reports
↓
suspicious_flags


# Database Tables

1. uploads Table

| Column                     | Meaning                      |
| -------------------------- | ---------------------------- |
| `id`                       | Unique upload identifier     |
| `filename`                 | Original uploaded file name  |
| `content_type`             | MIME type (`text/csv`)       |
| `file_size_bytes`          | File size                    |
| `file_hash`                | SHA256 hash of file contents |
| `status`                   | Processing result            |
| `duplicate_of_upload_id`   | If same file uploaded again  |
| `original_headers`         | CSV column names             |
| `total_rows`               | Total CSV rows               |
| `raw_rows_stored`          | Rows inserted into raw table |
| `accepted_rows`            | Successfully validated rows  |
| `rejected_rows`            | Invalid rows                 |
| `deduplicated_rows`        | Duplicate rows removed       |
| `suspicious_reports_count` | Flagged reports count        |
| `summary_json`             | Aggregated analytics         |
| `created_at`               | Upload timestamp             |
| `processed_at`             | Completion timestamp         |


File hash is used for Duplicate File Detection :

If same CSV is uploaded twice:
    hash(file1) == hash(file2)

Why hashing instead of filename?  --->    Because filenames can change.

Why SHA-256? ---> collision resistant, fast enough, industry standard



2. raw_report_rows

To Store EXACTLY what came from CSV before cleaning. This is critical in healthcare systems.
What if validator had a bug?

| Column                   | Meaning                      |
| ------------------------ | ---------------------------- |
| `id`                     | Primary key for raw row      |
| `upload_id`              | Upload batch/file reference  |
| `row_number`             | Original CSV row number      |
| `raw_data`               | Original raw CSV row         |
| `normalized_data`        | Cleaned/normalized row data  |
| `validation_status`      | Validation processing status |
| `rejection_reason_codes` | Validation failure codes     |
| `created_at`             | Ingestion timestamp          |

Because raw CSV data is messy but important, So store raw first and then normalize.

3. cbc_reports
This is our golden validated dataset.

| Column            | Meaning                          |
| ----------------- | -------------------------------- |
| `id`              | Primary key for clean CBC report |
| `upload_id`       | Upload batch/file reference      |
| `source_row_id`   | Link to original raw row         |
| `row_fingerprint` | Hash used for row deduplication  |
| `patient_id`      | Normalized patient identifier    |
| `patient_name`    | Patient name                     |
| `age`             | Validated patient age            |
| `gender`          | Normalized gender (`M`/`F`)      |
| `hemoglobin`      | Hemoglobin value                 |
| `wbc`             | White blood cell count           |
| `platelets`       | Platelet count                   |
| `test_date`       | Report/test date                 |
| `machine_id`      | Diagnostic machine identifier    |
| `created_at`      | Insert timestamp                 |

Why row_fingerprint? ---> Hashing normalized row -> SHA256(canonical_row_string) -> creates fingerprint.
If same fingerprint exists even in different csv files:
    duplicate row.


4. rejected_reports
This table stores rows that failed validation.

| Column            | Meaning                               |
| ----------------- | ------------------------------------- |
| `id`              | Unique rejected record ID             |
| `upload_id`       | Upload this rejected row belongs to   |
| `raw_row_id`      | Link to raw ingested row              |
| `row_number`      | Original CSV row number               |
| `raw_data`        | Original unmodified CSV data          |
| `normalized_data` | Cleaned/typed version of data         |
| `reason_codes`    | Machine-readable rejection codes      |
| `reason_details`  | Human-readable rejection explanations |
| `created_at`      | Rejection timestamp                   |


reason_details ---> to help understand why this particular row has been rejected

5. suspicious_flags
This is NOT rejected data. This is Valid BUT medically suspicious. Very important distinction.

| Column       | Meaning                            |
| ------------ | ---------------------------------- |
| `id`         | Unique suspicious flag ID          |
| `upload_id`  | Upload that generated the flag     |
| `report_id`  | Linked validated report ID         |
| `code`       | Machine-readable anomaly code      |
| `severity`   | Importance level of anomaly        |
| `message`    | Human-readable anomaly explanation |
| `details`    | Additional anomaly metadata        |
| `created_at` | Flag generation timestamp          |

This distinction is the key: Invalid ≠ Suspicious


-----------------------------------------------------------------------------------------------------------------


# Detailed pipeline:

CSV file
   ↓
File-level validation
   ↓
Parse each row
   ↓
Insert EVERY parsed row into raw_report_rows
   ↓
Run row validation + normalization
   ├── invalid → rejected_reports
   └── valid → deduplication
                    ├── duplicate → mark deduplicated / skip insert
                    └── clean → insert into cbc_reports
                                      ↓
                              suspicious flag checks
                                      ↓
                              suspicious_flags


# File-level acceptance rules
The upload is accepted for processing only if all of these are true:

1. file extension is .csv
2. file is not empty
3. file is valid UTF-8 / UTF-8 with BOM (utf-8-sig)
4. CSV has a header row
5. header contains all required columns:
6. patient_id
7. patient_name
8. age
9. gender
10. hemoglobin
11. wbc
12. platelets
13. test_date
14. machine_id

Extra columns are allowed and ignored for clean ingestion; they do not cause rejection. Blank lines are ignored.


# Row-level acceptance rules
A row is accepted into clean reports only if all of these are true:

1. every required field is present and non-empty
2. patient_id length is <= 100
3. patient_name length is <= 255
4. machine_id length is <= 100
4. age is numeric and a whole number
    age >= 0
    age <= 120
5. gender is one of:
    M
    F
    Male
    Female
6. hemoglobin is numeric
    hemoglobin > 0
    hemoglobin <= 25.0
7. wbc is numeric
    wbc > 0
    wbc <= 500000
8. platelets is numeric
    platelets > 0
    platelets <= 5000000
9. test_date parses successfully in one of these formats:
    YYYY-MM-DD
    YYYY/MM/DD
    DD-MM-YYYY
    DD/MM/YYYY
    MM/DD/YYYY
    test_date is not in the future

If a row passes all of the above, it is normalized, deduplicated, and then inserted.

# Row-level rejection rules
A row is rejected and moved to rejected_reports if any of the following happens:

1. one or more required fields are missing
2. patient_id is longer than 100 chars
3. patient_name is longer than 255 chars
4. machine_id is longer than 100 chars
5. age is not numeric
6. age is numeric but not an integer
    age < 0
    age > 120
7. gender is not one of M/F/Male/Female
8. hemoglobin is not numeric
    hemoglobin <= 0
    hemoglobin > 25.0
9. wbc is not numeric
    wbc <= 0
    wbc > 500000
10. platelets is not numeric
    platelets <= 0
    platelets > 5000000
11. test_date cannot be parsed
12. test_date is a future date

Each rejected row stores:

    original raw row
    row number
    rejection reason codes
    rejection reason details
    So one bad row does not crash the upload; only that row is rejected


# Normalization rules
For valid rows, these normalization rules are applied before deduplication and insert:

    header names are normalized to lowercase underscore form
    leading/trailing whitespace is trimmed on all values
    internal repeated whitespace is collapsed
    patient_id is uppercased
    machine_id is uppercased
    gender is normalized to M or F
    hemoglobin, wbc, platelets are stored as floats rounded to 2 decimals
    test_date is stored as a proper date
    only the required clean fields are inserted into cbc_reports


# Deduplication rules
There are two separate duplicate checks.

1) Duplicate file check
Before parsing rows, the backend computes a SHA-256 hash of the uploaded file.

If that same file hash already exists in a prior upload:

the new upload is marked DUPLICATE
processing is skipped
the response returns duplicate_of_upload_id
This handles “same CSV uploaded twice”

2) Duplicate row check
For valid rows, a row fingerprint is built from:

patient_id
test_date
machine_id
hemoglobin
wbc
platelets
If the fingerprint already exists:

earlier in the same batch, or
in previously inserted clean reports
then that row is marked DEDUPLICATED and is not inserted again.

This means exact repeats are removed, but conflicting results are preserved and flagged instead of silently dropped.


# Suspicious detection / flagging rules
Rows that are valid can still be suspicious. Those are accepted into clean reports and then flagged.

Abnormal reference-range flags
The code creates flags if:

1. Male hemoglobin is outside 13.0 – 17.0
2. Female hemoglobin is outside 12.0 – 15.0
3. WBC is outside 4000 – 11000
4. Platelets are outside 150000 – 450000
5. Age is above the reference guidance max of 100 years


Same-day cross-machine conflict flags
    If the same patient has same-day reports from different machines, and the values differ materially, both reports get a conflict flag.

Conflict thresholds used:
1. hemoglobin delta >= 2.0
2. or WBC delta >= 3000
    WBC relative delta >= 30%
3. platelets delta >= 50000
    platelets relative delta >= 30%
This is how the backend handles “same patient + same date but conflicting values across machines.”

Sudden-change flags
    A newly inserted report is compared with the most recent earlier report for the same patient.

Flags are created when:
1. hemoglobin delta >= 2.5
2. WBC delta >= 3000 and relative delta >= 50%
3. platelets delta >= 75000 and relative delta >= 50%
This covers the “data suddenly changes drastically” requirement.
