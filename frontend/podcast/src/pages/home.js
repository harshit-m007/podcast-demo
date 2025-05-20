import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './home.css';

const PodcastGenerator = () => {
  const [textInput, setTextInput] = useState('');
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
      const response = await axios.post(`${API_BASE_URL}/generate-from-text`, {
        text: textInput
      });

      setJobId(response.data.job_id);
      setJobStatus(response.data.status);
    } catch (err) {
      setError(err.response?.data?.detail || 'Error starting podcast generation');
      setJobStatus('failed');
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
              disabled={jobStatus === 'running' || !textInput.trim()}
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
        <div className="analysis-section">
          {analysis ? (
            <>
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

              <div className="analysis-card">
                <h3><i className="fas fa-flag-checkered"></i> Conclusions</h3>
                <div className="soundbite-container">
                  {analysis.conclusions.map((conclusion, index) => (
                    <div key={`conclusion-${index}`} className="soundbite-item">
                      <p>{conclusion}</p>
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
            <p>No analysis available.</p>
          )}
        </div>
      )}
    </div>
  );
};

export default PodcastGenerator;
