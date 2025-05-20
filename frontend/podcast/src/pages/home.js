import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './home.css';

const PodcastGenerator = () => {
  const [inputType, setInputType] = useState('text');
  const [textInput, setTextInput] = useState('');
  const [pdfFile, setPdfFile] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [progress, setProgress] = useState(0);
  const [podcastUrl, setPodcastUrl] = useState(null);
  const [error, setError] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [activeTab, setActiveTab] = useState('input');

  const API_BASE_URL = 'http://127.0.0.1:8000';

  useEffect(() => {
    let interval;
    if (jobId) {
      interval = setInterval(() => {
        checkJobStatus(jobId);
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [jobId]);

  const checkJobStatus = async (jobId) => {
    try {
      const response = await axios.get(`${API_BASE_URL}/job-status/${jobId}`);
      setJobStatus(response.data.status);
      
      if (response.data.status === 'completed') {
        setProgress(100);
        setPodcastUrl(`${API_BASE_URL}/download-podcast/${jobId}`);
        // Fetch analysis data when job is complete
        fetchAnalysisData(jobId);
      } else if (response.data.status === 'failed') {
        setError(response.data.message || 'Podcast generation failed');
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Error checking job status');
    }
  };

  const fetchAnalysisData = async (jobId) => {
    try {
      // This assumes your backend stores analysis data in the output directory
      // You might need to modify your backend to expose this via an API endpoint
      const response = await axios.get(`${API_BASE_URL}/get-analysis/${jobId}`);
      setAnalysis(response.data);
    } catch (err) {
      console.error("Couldn't fetch analysis data:", err);
    }
  };

  const handleGeneratePodcast = async () => {
    setError(null);
    setJobStatus('starting');
    setProgress(0);
    setPodcastUrl(null);
    setAnalysis(null);

    try {
      let response;
      
      if (inputType === 'text') {
        response = await axios.post(`${API_BASE_URL}/generate-from-text`, {
          text: textInput
        });
      } else {
        const formData = new FormData();
        formData.append('file', pdfFile);
        response = await axios.post(`${API_BASE_URL}/generate-from-pdf`, formData, {
          headers: {
            'Content-Type': 'multipart/form-data'
          }
        });
      }
      
      setJobId(response.data.job_id);
      setJobStatus(response.data.status);
    } catch (err) {
      setError(err.response?.data?.detail || 'Error starting podcast generation');
      setJobStatus('failed');
    }
  };

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (file && file.type === 'application/pdf') {
      setPdfFile(file);
    } else {
      setError('Please upload a valid PDF file');
    }
  };

  useEffect(() => {
    if (jobStatus === 'queued') setProgress(10);
    if (jobStatus === 'running') setProgress(50);
    if (jobStatus === 'completed') setProgress(100);
  }, [jobStatus]);

  return (
    <div className="podcast-generator">
      <header className="generator-header">
        <h1>Podcast Ai</h1>
        <p>Transform your content into professional audio podcasts and get highlights</p>
      </header>

      <div className="content-tabs">
        <button 
          className={`tab-btn ${activeTab === 'input' ? 'active' : ''}`}
          onClick={() => setActiveTab('input')}
        >
          <i className="fas fa-microphone-alt"></i> Create Podcast
        </button>
        <button 
          className={`tab-btn ${activeTab === 'results' ? 'active' : ''}`}
          onClick={() => setActiveTab('results')}
          disabled={!podcastUrl}
        >
          <i className="fas fa-chart-bar"></i> Analysis
        </button>
      </div>

      {error && (
        <div className="error-message">
          <i className="fas fa-exclamation-circle"></i> {error}
        </div>
      )}

      {activeTab === 'input' ? (
        <div className="input-section">
          <div className="input-selector">
            <button
              className={`selector-btn ${inputType === 'text' ? 'active' : ''}`}
              onClick={() => setInputType('text')}
            >
              <i className="fas fa-align-left"></i> Text Input
            </button>
            <button
              className={`selector-btn ${inputType === 'pdf' ? 'active' : ''}`}
              onClick={() => setInputType('pdf')}
            >
              <i className="fas fa-file-pdf"></i> PDF Upload
            </button>
          </div>

          {inputType === 'text' ? (
            <div className="text-input-container">
              <textarea
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                placeholder="Paste your article, blog post, or any text content here..."
                className="text-input"
                rows="10"
                disabled={jobStatus === 'running'}
              />
              <div className="text-input-footer">
                <span className="word-count">
                  {textInput.split(/\s+/).filter(Boolean).length} words
                </span>
                <button 
                  className="clear-btn"
                  onClick={() => setTextInput('')}
                  disabled={jobStatus === 'running'}
                >
                  <i className="fas fa-trash-alt"></i> Clear
                </button>
              </div>
            </div>
          ) : (
            <div className="file-upload-container">
              {!pdfFile ? (
                <div className="upload-box">
                  <i className="fas fa-cloud-upload-alt upload-icon"></i>
                  <h3>Upload PDF File</h3>
                  <p>Drag & drop your PDF here or click to browse</p>
                  <input 
                    type="file" 
                    id="pdf-upload" 
                    accept=".pdf" 
                    onChange={handleFileUpload}
                    disabled={jobStatus === 'running'}
                    hidden
                  />
                  <label htmlFor="pdf-upload" className="browse-btn">
                    Select File
                  </label>
                </div>
              ) : (
                <div className="file-preview">
                  <div className="file-icon">
                    <i className="fas fa-file-pdf"></i>
                  </div>
                  <div className="file-info">
                    <p className="file-name">{pdfFile.name}</p>
                    <p className="file-size">{(pdfFile.size / 1024 / 1024).toFixed(2)} MB</p>
                  </div>
                  <button 
                    className="remove-file"
                    onClick={() => setPdfFile(null)}
                    disabled={jobStatus === 'running'}
                  >
                    Remove
                  </button>
                </div>
              )}
            </div>
          )}

          {jobStatus && (
            <div className="progress-container">
              <div className="progress-bar" style={{ width: `${progress}%` }}></div>
              <div className="status-message">
                {jobStatus === 'queued' && 'Job queued...'}
                {jobStatus === 'running' && 'Generating podcast...'}
                {jobStatus === 'completed' && 'Podcast ready!'}
                {jobStatus === 'failed' && 'Generation failed'}
              </div>
            </div>
          )}

          <div className="generate-section">
            <button 
              className="generate-btn"
              onClick={handleGeneratePodcast}
              disabled={
                jobStatus === 'running' || 
                (inputType === 'text' && !textInput.trim()) || 
                (inputType === 'pdf' && !pdfFile)
              }
            >
              <i className="fas fa-microphone-alt"></i> Generate Podcast
            </button>
          </div>

          {podcastUrl && (
            <div className="result-section">
              <h3>Your Podcast is Ready!</h3>
              <div className="audio-player">
                <audio controls src={podcastUrl}></audio>
                <a 
                  href={podcastUrl} 
                  download="podcast.mp3" 
                  className="download-btn"
                >
                  <i className="fas fa-download"></i> Download
                </a>
              </div>
            </div>
          )}
        </div>
      ) : (
        // Add this to your analysis display section (replace your current analysis card)
<div className="analysis-section">
  {analysis ? (
    <>
      {/* Key Points with Audio */}
      <div className="analysis-card">
        <h3><i className="fas fa-key"></i> Key Points</h3>
        <div className="soundbite-container">
          {analysis.key_points.map((point, index) => (
            <div key={`keypoint-${index}`} className="soundbite-item">
              <p>{point}</p>
              <audio 
                controls 
                src={`${API_BASE_URL}/soundbites/${jobId}/keypoint_${index}.mp3`}
                className="soundbite-player"
              />
            </div>
          ))}
        </div>
      </div>
      
      {/* Major Issues with Audio */}
      <div className="analysis-card">
        <h3><i className="fas fa-exclamation-circle"></i> Major Issues</h3>
        <div className="soundbite-container">
          {analysis.major_issues.map((issue, index) => (
            <div key={`issue-${index}`} className="soundbite-item">
              <p>{issue}</p>
              <audio 
                controls 
                src={`${API_BASE_URL}/soundbites/${jobId}/issue_${index}.mp3`}
                className="soundbite-player"
              />
            </div>
          ))}
        </div>
      </div>
      
      {/* Conclusions with Audio */}
      <div className="analysis-card">
        <h3><i className="fas fa-flag-checkered"></i> Conclusions</h3>
        <div className="soundbite-container">
          {analysis.conclusions.map((conclusion, index) => (
            <div key={`conclusion-${index}`} className="soundbite-item">
              <p>Conclusion: {conclusion}</p>
              <audio 
                controls 
                src={`${API_BASE_URL}/soundbites/${jobId}/conclusion_${index}.mp3`}
                className="soundbite-player"
              />
            </div>
          ))}
        </div>
      </div>
    </>
  ) : (
    <div className="no-analysis">
      <i className="fas fa-chart-pie"></i>
      <p>No analysis data available yet</p>
    </div>
  )}
</div>
      )}

      <footer className="generator-footer">
        <p>© {new Date().getFullYear()} Podcast AI. All rights reserved.</p>
      </footer>
    </div>
  );
};

export default PodcastGenerator;