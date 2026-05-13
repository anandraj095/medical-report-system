import { useEffect, useMemo, useState } from 'react';
import {
  getAnalytics,
  getApiBaseUrl,
  getReports,
  getTemplate,
  getUploadDetails,
  uploadCsv
} from './api';

const defaultFilters = {
  page: 1,
  page_size: 10,
  search: '',
  patient_id: '',
  machine_id: '',
  suspicious_only: false,
  flag_code: '',
  date_from: '',
  date_to: '',
  sort_by: 'test_date',
  sort_order: 'desc'
};

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [analytics, setAnalytics] = useState(null);
  const [template, setTemplate] = useState(null);
  const [reportsPage, setReportsPage] = useState({ items: [], total: 0, total_pages: 0, page: 1, page_size: 10 });
  const [filters, setFilters] = useState(defaultFilters);
  const [draftFilters, setDraftFilters] = useState(defaultFilters);

  const [loadingDashboard, setLoadingDashboard] = useState(true);
  const [loadingReports, setLoadingReports] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [loadingUploadDetail, setLoadingUploadDetail] = useState(false);

  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadSummary, setUploadSummary] = useState(null);
  const [uploadError, setUploadError] = useState('');

  const [uploadLookupId, setUploadLookupId] = useState('');
  const [uploadDetail, setUploadDetail] = useState(null);
  const [uploadDetailError, setUploadDetailError] = useState('');

  const apiBaseUrl = getApiBaseUrl();

  const flagCodeSuggestions = useMemo(() => {
    const codes = new Set();

    (analytics?.top_abnormality_reasons || []).forEach((item) => {
      if (item.reason) codes.add(item.reason);
    });

    (reportsPage.items || []).forEach((report) => {
      (report.flags || []).forEach((flag) => {
        if (flag.code) codes.add(flag.code);
      });
    });

    return Array.from(codes).sort();
  }, [analytics, reportsPage]);

  useEffect(() => {
    initializePage();
  }, []);

  async function initializePage() {
    await Promise.all([loadDashboard(), loadReports(defaultFilters)]);
  }

  async function loadDashboard() {
    setLoadingDashboard(true);
    try {
      const [analyticsData, templateData] = await Promise.all([getAnalytics(), getTemplate()]);
      setAnalytics(analyticsData);
      setTemplate(templateData);
    } catch (error) {
      setUploadError(error.message || 'Failed to load dashboard data.');
    } finally {
      setLoadingDashboard(false);
    }
  }

  async function loadReports(nextFilters = filters) {
    setLoadingReports(true);
    try {
      const data = await getReports({
        ...nextFilters,
        suspicious_only: nextFilters.suspicious_only ? 'true' : ''
      });
      setReportsPage(data);
      setFilters(nextFilters);
    } catch (error) {
      setUploadError(error.message || 'Failed to load reports.');
    } finally {
      setLoadingReports(false);
    }
  }

  async function loadUploadInvestigation(uploadId) {
    if (!uploadId) {
      setUploadDetail(null);
      setUploadDetailError('Please enter an upload ID.');
      return;
    }

    setLoadingUploadDetail(true);
    setUploadDetailError('');

    try {
      const data = await getUploadDetails(uploadId);
      setUploadDetail(data);
      setUploadLookupId(String(uploadId));
    } catch (error) {
      setUploadDetail(null);
      setUploadDetailError(error.message || 'Failed to load upload details.');
    } finally {
      setLoadingUploadDetail(false);
    }
  }

  async function handleUpload(event) {
    event.preventDefault();

    if (!selectedFile) {
      setUploadError('Please choose a CSV file first.');
      return;
    }

    setUploading(true);
    setUploadError('');
    setUploadSummary(null);

    try {
      const summary = await uploadCsv(selectedFile);
      setUploadSummary(summary);
      setUploadLookupId(String(summary.upload_id));
      setActiveTab('uploads');
      await Promise.all([
        loadDashboard(),
        loadReports({ ...filters, page: 1 }),
        loadUploadInvestigation(summary.upload_id)
      ]);
    } catch (error) {
      const detailUploadId = error?.detail?.upload_id;
      setUploadError(error.message || 'Upload failed.');
      if (detailUploadId) {
        setUploadLookupId(String(detailUploadId));
        await loadUploadInvestigation(detailUploadId);
      }
    } finally {
      setUploading(false);
    }
  }

  function handleFilterChange(key, value) {
    setDraftFilters((previous) => ({ ...previous, [key]: value }));
  }

  function applyFilters(event) {
    event.preventDefault();
    loadReports({ ...draftFilters, page: 1 });
  }

  function resetFilters() {
    setDraftFilters(defaultFilters);
    loadReports(defaultFilters);
  }

  function changePage(nextPage) {
    if (nextPage < 1 || nextPage > reportsPage.total_pages) return;
    const nextFilters = { ...filters, page: nextPage };
    setDraftFilters(nextFilters);
    loadReports(nextFilters);
  }

  const templateCsvExample = useMemo(() => {
    if (!template?.required_columns || !template?.example) return '';
    const header = template.required_columns.join(',');
    const row = template.required_columns.map((column) => template.example[column] ?? '').join(',');
    return `${header}\n${row}`;
  }, [template]);

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">React frontend for your FastAPI backend</p>
          <h1>Medical Report Review & Exception Handling System</h1>
          <p className="hero-copy">
            This UI covers CSV upload, report review, suspicious flag inspection, analytics, and upload investigation.
          </p>
        </div>
        <div className="hero-meta card subtle-card">
          <p><strong>Backend API:</strong> {apiBaseUrl}</p>
          <p><strong>Main flows:</strong> Upload CSV → Review reports → Inspect suspicious cases → Investigate failures</p>
        </div>
      </header>

      <nav className="tab-row">
        <TabButton label="Dashboard" active={activeTab === 'dashboard'} onClick={() => setActiveTab('dashboard')} />
        <TabButton label="Upload & Investigation" active={activeTab === 'uploads'} onClick={() => setActiveTab('uploads')} />
        <TabButton label="Reports" active={activeTab === 'reports'} onClick={() => setActiveTab('reports')} />
      </nav>

      {uploadError ? <MessageBox tone="error" title="Action message" message={uploadError} /> : null}

      {activeTab === 'dashboard' ? (
        <section className="page-section">
          <SectionHeader
            title="System analytics"
            description="Live numbers coming from GET /analytics plus upload template help from GET /upload/template."
            action={
              <button className="secondary-button" onClick={loadDashboard} disabled={loadingDashboard}>
                {loadingDashboard ? 'Refreshing...' : 'Refresh dashboard'}
              </button>
            }
          />

          {loadingDashboard ? (
            <LoadingCard text="Loading analytics and template..." />
          ) : (
            <>
              <div className="stats-grid">
                <StatCard label="Total uploads" value={analytics?.total_uploads ?? 0} tone="blue" />
                <StatCard label="Processed uploads" value={analytics?.processed_uploads ?? 0} tone="green" />
                <StatCard label="Failed uploads" value={analytics?.failed_uploads ?? 0} tone="red" />
                <StatCard label="Duplicate uploads" value={analytics?.duplicate_uploads ?? 0} tone="yellow" />
                <StatCard label="Total reports" value={analytics?.total_reports ?? 0} tone="blue" />
                <StatCard label="Suspicious reports" value={analytics?.suspicious_reports ?? 0} tone="red" />
                <StatCard label="Abnormal reports" value={analytics?.abnormal_reports ?? 0} tone="yellow" />
                <StatCard label="Conflict reports" value={analytics?.conflict_reports ?? 0} tone="red" />
                <StatCard label="Sudden-change reports" value={analytics?.sudden_change_reports ?? 0} tone="yellow" />
                <StatCard label="Rejected rows" value={analytics?.total_rejected_rows ?? 0} tone="red" />
                <StatCard label="Deduplicated rows" value={analytics?.total_deduplicated_rows ?? 0} tone="yellow" />
                <StatCard label="Upload success %" value={`${analytics?.upload_success_ratio_percent ?? 0}%`} tone="green" />
              </div>

              <div className="two-column-grid">
                <Card title="Top suspicious reason codes" subtitle="Most frequent flag codes returned by the backend">
                  <ReasonList items={analytics?.top_abnormality_reasons || []} emptyText="No suspicious flags yet." />
                </Card>

                <Card title="Top rejection reason codes" subtitle="Most frequent row-level validation failures">
                  <ReasonList items={analytics?.top_rejection_reasons || []} emptyText="No rejected rows yet." />
                </Card>
              </div>

              <div className="two-column-grid">
                <Card title="CSV upload template" subtitle="Required columns from the backend template endpoint">
                  <div className="chip-wrap">
                    {(template?.required_columns || []).map((column) => (
                      <span key={column} className="chip neutral-chip">{column}</span>
                    ))}
                  </div>
                  <label className="field-label">Example CSV you can paste into a file</label>
                  <pre className="code-block">{templateCsvExample || 'Template example unavailable.'}</pre>
                </Card>

                <Card title="Frontend coverage" subtitle="Everything available in your backend is exposed here">
                  <ul className="feature-list">
                    <li>Upload CSV files through the UI</li>
                    <li>Review upload summaries, duplicates, and processing status</li>
                    <li>Inspect rejected rows and exact validation reasons</li>
                    <li>Search, sort, paginate, and filter processed reports</li>
                    <li>Focus only on suspicious reports or a single flag code</li>
                    <li>Review analytics without using Swagger UI</li>
                  </ul>
                </Card>
              </div>
            </>
          )}
        </section>
      ) : null}

      {activeTab === 'uploads' ? (
        <section className="page-section uploads-layout">
          <div className="stack-gap">
            <SectionHeader
              title="Upload CSV reports"
              description="This form sends a multipart file upload to POST /upload."
            />
            <Card title="Upload a CBC CSV file" subtitle="Choose the same file you were testing in Swagger UI">
              <form onSubmit={handleUpload} className="stack-gap">
                <div className="upload-box">
                  <input
                    type="file"
                    accept=".csv,text/csv"
                    onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
                  />
                  <p className="muted-text">
                    Selected file: {selectedFile ? selectedFile.name : 'No file selected yet'}
                  </p>
                </div>
                <div className="button-row">
                  <button className="primary-button" type="submit" disabled={uploading}>
                    {uploading ? 'Uploading...' : 'Upload and process'}
                  </button>
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => {
                      setSelectedFile(null);
                      setUploadSummary(null);
                      setUploadError('');
                    }}
                  >
                    Clear
                  </button>
                </div>
              </form>
            </Card>

            {uploadSummary ? (
              <Card title="Latest upload summary" subtitle={`Upload ID ${uploadSummary.upload_id}`}>
                <div className="summary-grid">
                  <SummaryItem label="File name" value={uploadSummary.file_name} />
                  <SummaryItem label="Status" value={<StatusPill status={uploadSummary.status} />} />
                  <SummaryItem label="Duplicate file" value={uploadSummary.duplicate ? 'Yes' : 'No'} />
                  <SummaryItem label="Duplicate of upload" value={uploadSummary.duplicate_of_upload_id ?? '-'} />
                  <SummaryItem label="Total rows" value={uploadSummary.total_rows} />
                  <SummaryItem label="Accepted rows" value={uploadSummary.accepted_rows} />
                  <SummaryItem label="Rejected rows" value={uploadSummary.rejected_rows} />
                  <SummaryItem label="Deduplicated rows" value={uploadSummary.deduplicated_rows} />
                  <SummaryItem label="Suspicious reports" value={uploadSummary.suspicious_reports_count} />
                  <SummaryItem label="Message" value={uploadSummary.message} />
                </div>

                <div className="two-column-grid top-space">
                  <Card title="Rejected row breakdown" subtitle="Counts by reason code" compact>
                    <DictionaryView data={uploadSummary.rejected_breakdown} emptyText="No rejected rows in this upload." />
                  </Card>
                  <Card title="Suspicious flag breakdown" subtitle="Counts by suspicious code" compact>
                    <DictionaryView data={uploadSummary.flags_breakdown} emptyText="No suspicious flags in this upload." />
                  </Card>
                </div>

                <div className="button-row top-space">
                  <button
                    className="primary-button"
                    type="button"
                    onClick={() => loadUploadInvestigation(uploadSummary.upload_id)}
                  >
                    Open investigation view
                  </button>
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => setActiveTab('reports')}
                  >
                    Go to reports
                  </button>
                </div>
              </Card>
            ) : null}
          </div>

          <div className="stack-gap">
            <SectionHeader
              title="Upload investigation"
              description="This panel calls GET /uploads/{upload_id} to inspect failed rows and summaries."
            />

            <Card title="Load upload details" subtitle="Useful even when an upload partially fails">
              <form
                className="investigation-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  loadUploadInvestigation(uploadLookupId);
                }}
              >
                <div>
                  <label className="field-label">Upload ID</label>
                  <input
                    className="text-input"
                    value={uploadLookupId}
                    onChange={(event) => setUploadLookupId(event.target.value)}
                    placeholder="Example: 1"
                  />
                </div>
                <button className="primary-button" type="submit" disabled={loadingUploadDetail}>
                  {loadingUploadDetail ? 'Loading...' : 'Load details'}
                </button>
              </form>
              {uploadDetailError ? <MessageBox tone="error" title="Investigation error" message={uploadDetailError} compact /> : null}
            </Card>

            {uploadDetail ? (
              <Card title={`Investigation for upload ${uploadDetail.upload_id}`} subtitle={uploadDetail.filename}>
                <div className="summary-grid">
                  <SummaryItem label="Status" value={<StatusPill status={uploadDetail.status} />} />
                  <SummaryItem label="Created at" value={formatDateTime(uploadDetail.created_at)} />
                  <SummaryItem label="Processed at" value={formatDateTime(uploadDetail.processed_at)} />
                  <SummaryItem label="Rejected rows count" value={uploadDetail.rejected_reports.length} />
                </div>

                <div className="top-space">
                  <label className="field-label">Upload summary JSON</label>
                  <pre className="json-block">{prettyJson(uploadDetail.summary)}</pre>
                </div>

                <div className="top-space">
                  <label className="field-label">Rejected rows</label>
                  {uploadDetail.rejected_reports.length === 0 ? (
                    <div className="empty-state small-empty">No rejected rows for this upload.</div>
                  ) : (
                    <div className="stack-gap">
                      {uploadDetail.rejected_reports.map((row) => (
                        <details key={row.id} className="details-card">
                          <summary>
                            Row {row.row_number} · {row.reason_codes.join(', ')}
                          </summary>
                          <div className="details-content">
                            <div>
                              <label className="field-label">Reason details</label>
                              <pre className="json-block">{prettyJson(row.reason_details)}</pre>
                            </div>
                            <div>
                              <label className="field-label">Raw data</label>
                              <pre className="json-block">{prettyJson(row.raw_data)}</pre>
                            </div>
                            <div>
                              <label className="field-label">Normalized data</label>
                              <pre className="json-block">{prettyJson(row.normalized_data)}</pre>
                            </div>
                          </div>
                        </details>
                      ))}
                    </div>
                  )}
                </div>
              </Card>
            ) : (
              <Card title="How to use this investigation panel" subtitle="Simple workflow">
                <ol className="steps-list">
                  <li>Upload a CSV file on the left side.</li>
                  <li>Copy the upload ID from the summary.</li>
                  <li>Load that upload ID here.</li>
                  <li>Open each rejected row to inspect raw data and validation messages.</li>
                </ol>
              </Card>
            )}
          </div>
        </section>
      ) : null}

      {activeTab === 'reports' ? (
        <section className="page-section">
          <SectionHeader
            title="Processed reports"
            description="This view replaces the Swagger /reports testing workflow with a full filterable table."
            action={
              <button className="secondary-button" onClick={() => loadReports(filters)} disabled={loadingReports}>
                {loadingReports ? 'Refreshing...' : 'Refresh reports'}
              </button>
            }
          />

          <Card title="Filters, sorting, and pagination" subtitle="The controls map directly to the GET /reports query parameters">
            <form className="filters-grid" onSubmit={applyFilters}>
              <div>
                <label className="field-label">Search</label>
                <input
                  className="text-input"
                  value={draftFilters.search}
                  onChange={(event) => handleFilterChange('search', event.target.value)}
                  placeholder="Patient name, patient ID, or machine ID"
                />
              </div>
              <div>
                <label className="field-label">Patient ID</label>
                <input
                  className="text-input"
                  value={draftFilters.patient_id}
                  onChange={(event) => handleFilterChange('patient_id', event.target.value)}
                  placeholder="Example: P001"
                />
              </div>
              <div>
                <label className="field-label">Machine ID</label>
                <input
                  className="text-input"
                  value={draftFilters.machine_id}
                  onChange={(event) => handleFilterChange('machine_id', event.target.value)}
                  placeholder="Example: M1"
                />
              </div>
              <div>
                <label className="field-label">Flag code</label>
                <input
                  className="text-input"
                  list="flag-code-options"
                  value={draftFilters.flag_code}
                  onChange={(event) => handleFilterChange('flag_code', event.target.value)}
                  placeholder="Example: ABNORMAL_WBC_HIGH"
                />
                <datalist id="flag-code-options">
                  {flagCodeSuggestions.map((code) => (
                    <option value={code} key={code} />
                  ))}
                </datalist>
              </div>
              <div>
                <label className="field-label">Date from</label>
                <input
                  className="text-input"
                  type="date"
                  value={draftFilters.date_from}
                  onChange={(event) => handleFilterChange('date_from', event.target.value)}
                />
              </div>
              <div>
                <label className="field-label">Date to</label>
                <input
                  className="text-input"
                  type="date"
                  value={draftFilters.date_to}
                  onChange={(event) => handleFilterChange('date_to', event.target.value)}
                />
              </div>
              <div>
                <label className="field-label">Sort by</label>
                <select
                  className="text-input"
                  value={draftFilters.sort_by}
                  onChange={(event) => handleFilterChange('sort_by', event.target.value)}
                >
                  <option value="test_date">Test date</option>
                  <option value="patient_id">Patient ID</option>
                  <option value="patient_name">Patient name</option>
                  <option value="age">Age</option>
                  <option value="hemoglobin">Hemoglobin</option>
                  <option value="wbc">WBC</option>
                  <option value="platelets">Platelets</option>
                  <option value="machine_id">Machine ID</option>
                  <option value="created_at">Created at</option>
                  <option value="id">Report ID</option>
                </select>
              </div>
              <div>
                <label className="field-label">Sort order</label>
                <select
                  className="text-input"
                  value={draftFilters.sort_order}
                  onChange={(event) => handleFilterChange('sort_order', event.target.value)}
                >
                  <option value="desc">Descending</option>
                  <option value="asc">Ascending</option>
                </select>
              </div>
              <div>
                <label className="field-label">Page size</label>
                <select
                  className="text-input"
                  value={draftFilters.page_size}
                  onChange={(event) => handleFilterChange('page_size', Number(event.target.value))}
                >
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
              </div>
              <div className="checkbox-row filter-checkbox">
                <input
                  id="suspicious_only"
                  type="checkbox"
                  checked={draftFilters.suspicious_only}
                  onChange={(event) => handleFilterChange('suspicious_only', event.target.checked)}
                />
                <label htmlFor="suspicious_only">Suspicious reports only</label>
              </div>
              <div className="button-row filter-actions">
                <button className="primary-button" type="submit">Apply filters</button>
                <button className="secondary-button" type="button" onClick={resetFilters}>Reset</button>
              </div>
            </form>
          </Card>

          <Card
            title="Reports table"
            subtitle={`Showing ${reportsPage.items.length} row(s) out of ${reportsPage.total} total report(s)`}
          >
            {loadingReports ? (
              <LoadingCard text="Loading reports..." />
            ) : reportsPage.items.length === 0 ? (
              <div className="empty-state">No reports matched the current filters.</div>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Upload</th>
                      <th>Patient</th>
                      <th>Age / Gender</th>
                      <th>Hemoglobin</th>
                      <th>WBC</th>
                      <th>Platelets</th>
                      <th>Test date</th>
                      <th>Machine</th>
                      <th>Flags</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reportsPage.items.map((report) => (
                      <tr key={report.id}>
                        <td>{report.id}</td>
                        <td>
                          <button
                            className="link-button"
                            type="button"
                            onClick={() => {
                              setActiveTab('uploads');
                              loadUploadInvestigation(report.upload_id);
                            }}
                          >
                            {report.upload_id}
                          </button>
                        </td>
                        <td>
                          <div className="patient-cell">
                            <strong>{report.patient_name}</strong>
                            <span>{report.patient_id}</span>
                          </div>
                        </td>
                        <td>{report.age} / {report.gender}</td>
                        <td>{formatNumber(report.hemoglobin)}</td>
                        <td>{formatNumber(report.wbc)}</td>
                        <td>{formatNumber(report.platelets)}</td>
                        <td>{report.test_date}</td>
                        <td>{report.machine_id}</td>
                        <td>
                          {report.flags?.length ? (
                            <div className="flag-list">
                              {report.flags.map((flag) => (
                                <details key={flag.id} className="inline-flag-card">
                                  <summary>
                                    <SeverityPill severity={flag.severity} />
                                    <span>{flag.code}</span>
                                  </summary>
                                  <div className="flag-body">
                                    <p>{flag.message}</p>
                                    <pre className="json-block small-json">{prettyJson(flag.details)}</pre>
                                  </div>
                                </details>
                              ))}
                            </div>
                          ) : (
                            <span className="muted-text">No flags</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="pagination-row">
              <button className="secondary-button" type="button" onClick={() => changePage(filters.page - 1)}>
                Previous
              </button>
              <span>
                Page {reportsPage.page || 1} of {reportsPage.total_pages || 1}
              </span>
              <button className="secondary-button" type="button" onClick={() => changePage(filters.page + 1)}>
                Next
              </button>
            </div>
          </Card>
        </section>
      ) : null}
    </div>
  );
}

function TabButton({ label, active, onClick }) {
  return (
    <button className={`tab-button ${active ? 'active-tab' : ''}`} onClick={onClick} type="button">
      {label}
    </button>
  );
}

function SectionHeader({ title, description, action = null }) {
  return (
    <div className="section-header">
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}

function Card({ title, subtitle, children, compact = false }) {
  return (
    <section className={`card ${compact ? 'compact-card' : ''}`}>
      <div className="card-head">
        <div>
          <h3>{title}</h3>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
      </div>
      {children}
    </section>
  );
}

function StatCard({ label, value, tone }) {
  return (
    <div className={`stat-card stat-${tone}`}>
      <p>{label}</p>
      <h3>{value}</h3>
    </div>
  );
}

function SummaryItem({ label, value }) {
  return (
    <div className="summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ReasonList({ items, emptyText }) {
  if (!items.length) {
    return <div className="empty-state small-empty">{emptyText}</div>;
  }

  return (
    <div className="reason-list">
      {items.map((item) => (
        <div className="reason-row" key={`${item.reason}-${item.count}`}>
          <span>{item.reason}</span>
          <strong>{item.count}</strong>
        </div>
      ))}
    </div>
  );
}

function DictionaryView({ data, emptyText }) {
  const entries = Object.entries(data || {});

  if (!entries.length) {
    return <div className="empty-state small-empty">{emptyText}</div>;
  }

  return (
    <div className="reason-list">
      {entries.map(([key, value]) => (
        <div className="reason-row" key={key}>
          <span>{key}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function MessageBox({ title, message, tone = 'info', compact = false }) {
  return (
    <div className={`message-box ${tone} ${compact ? 'compact-message' : ''}`}>
      <strong>{title}</strong>
      <p>{message}</p>
    </div>
  );
}

function LoadingCard({ text }) {
  return <div className="loading-card">{text}</div>;
}

function StatusPill({ status }) {
  const normalized = String(status || '').toUpperCase();
  const className =
    normalized.includes('FAILED')
      ? 'status-pill status-red'
      : normalized.includes('DUPLICATE')
        ? 'status-pill status-yellow'
        : normalized.includes('ERROR')
          ? 'status-pill status-yellow'
          : 'status-pill status-green';

  return <span className={className}>{status}</span>;
}

function SeverityPill({ severity }) {
  const normalized = String(severity || '').toLowerCase();
  const className =
    normalized === 'high'
      ? 'severity-pill severity-high'
      : normalized === 'medium'
        ? 'severity-pill severity-medium'
        : 'severity-pill severity-low';

  return <span className={className}>{severity}</span>;
}

function formatDateTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatNumber(value) {
  if (value === null || value === undefined || value === '') return '-';
  return new Intl.NumberFormat().format(value);
}

function prettyJson(value) {
  if (value === null || value === undefined) return 'null';
  return JSON.stringify(value, null, 2);
}

export default App;
