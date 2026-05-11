import { useState } from 'react';
import Stage1, { Stage1Skeleton } from './Stage1';
import Stage2, { Stage2Skeleton } from './Stage2';
import Stage3, { Stage3Skeleton } from './Stage3';
import ReactMarkdown from 'react-markdown';
import './AutocouncilResults.css';

function RoundTab({ round, active, onClick, status }) {
    const statusIcon = status === 'running' ? '⟳' : status === 'complete' ? '✓' : '○';
    const statusClass = status === 'running' ? 'running' : status === 'complete' ? 'complete' : 'pending';
    return (
        <button
            className={`autocouncil-round-tab ${active ? 'active' : ''} ${statusClass}`}
            onClick={onClick}
        >
            <span className="round-tab-icon">{statusIcon}</span>
            <span className="round-tab-label">Round {round}</span>
        </button>
    );
}

export default function AutocouncilResults({ message }) {
    const [activeRound, setActiveRound] = useState(0);
    const { autocouncil } = message;

    if (!autocouncil) return null;

    const { rounds = [], converged, convergenceReason, finalSynthesis, loading } = autocouncil;

    // Determine which round tab is active: if rounds are complete, show last round
    // Otherwise show the currently loading round
    const displayRounds = rounds.length > 0 ? rounds : [{ round: 1 }];
    const currentRoundIndex = Math.min(activeRound, displayRounds.length - 1);

    // Render loading indicator for the current stage
    const renderStageLoading = (stage) => {
        if (!loading || loading.currentRound !== displayRounds[currentRoundIndex]?.round) return null;
        if (loading.currentStage !== stage) return null;
        if (stage === 'stage1') return <Stage1Skeleton />;
        if (stage === 'stage2') return <Stage2Skeleton />;
        if (stage === 'stage3') return <Stage3Skeleton />;
        return null;
    };

    const currentRound = displayRounds[currentRoundIndex];

    return (
        <div className="autocouncil-results glass-panel">
            {/* Convergence Banner */}
            {converged && (
                <div className="autocouncil-convergence-banner">
                    <span className="convergence-icon">🎯</span>
                    <div className="convergence-text">
                        <strong>Convergence Reached</strong>
                        {convergenceReason && <span className="convergence-reason">— {convergenceReason}</span>}
                    </div>
                </div>
            )}

            {/* Round Tabs */}
            <div className="autocouncil-round-tabs">
                {displayRounds.map((round, idx) => {
                    const isComplete = round.complete || round.stage3;
                    const isRunning = !isComplete && (loading?.currentRound === round.round);
                    const status = isComplete ? 'complete' : isRunning ? 'running' : 'pending';
                    return (
                        <RoundTab
                            key={round.round || idx}
                            round={round.round || idx + 1}
                            active={idx === currentRoundIndex}
                            status={status}
                            onClick={() => setActiveRound(idx)}
                        />
                    );
                })}
            </div>

            {/* Round Content */}
            <div className="autocouncil-round-content">
                {/* Round Header */}
                <div className="autocouncil-round-header">
                    <h4>
                        {currentRound.round
                            ? `Round ${currentRound.round}`
                            : `Initial Deliberation`}
                    </h4>
                    {currentRound.answer && (
                        <div className="round-answer-preview">
                            <span className="answer-label">Round Answer:</span>
                            <ReactMarkdown>{currentRound.answer}</ReactMarkdown>
                        </div>
                    )}
                </div>

                {/* Stage 1: Council Deliberation */}
                <div className="autocouncil-stage-section">
                    <h5 className="autocouncil-stage-title stage1">
                        Stage 1: Council Responses
                    </h5>
                    {currentRound.stage1 ? (
                        <Stage1 responses={currentRound.stage1} />
                    ) : (
                        renderStageLoading('stage1')
                    )}
                </div>

                {/* Stage 2: Peer Ranking */}
                <div className="autocouncil-stage-section">
                    <h5 className="autocouncil-stage-title stage2">
                        Stage 2: Peer Ranking
                    </h5>
                    {currentRound.stage2 ? (
                        <Stage2
                            rankings={currentRound.stage2}
                            labelToModel={currentRound.metadata?.label_to_model}
                            aggregateRankings={currentRound.metadata?.aggregate_rankings}
                        />
                    ) : (
                        renderStageLoading('stage2')
                    )}
                </div>

                {/* Stage 3: Synthesis */}
                <div className="autocouncil-stage-section">
                    <h5 className="autocouncil-stage-title stage3">
                        Stage 3: Chairman Synthesis
                    </h5>
                    {currentRound.stage3 ? (
                        <Stage3 finalResponse={currentRound.stage3} />
                    ) : (
                        renderStageLoading('stage3')
                    )}
                </div>
            </div>

            {/* Final Synthesis (shown after convergence) */}
            {converged && finalSynthesis && (
                <div className="autocouncil-final-synthesis">
                    <h4 className="final-synthesis-title">Final Consensus</h4>
                    <div className="final-synthesis-content">
                        <ReactMarkdown>{finalSynthesis}</ReactMarkdown>
                    </div>
                </div>
            )}

            {/* Still running indicator */}
            {!converged && loading && (
                <div className="autocouncil-running-indicator">
                    <div className="spinner"></div>
                    <span>
                        Auto-deliberation in progress — Round {loading.currentRound || 1}
                        {loading.currentStage && ` (${loading.currentStage})`}
                    </span>
                </div>
            )}
        </div>
    );
}
